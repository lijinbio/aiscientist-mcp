"""Bound inputs and isolated, repeatable CellQC jobs using the shared executors."""

import contextlib
import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path

from aiscientist_mcp.common import jobs
from aiscientist_mcp.common.paths import child_dir, safe_id

from . import __version__
from .settings import defaults_source

ACTIVE = {"PENDING", "RUNNING", "CONFIGURING", "COMPLETING", "SUSPENDED", "UNKNOWN"}


def workspace(analysis_id: str) -> Path:
    if analysis_id == ".":
        raise ValueError("invalid analysis_id")
    root = Path(os.environ.get("AISCI_DATA_DIR", "./data")).resolve() / "cellqc"
    root.mkdir(parents=True, exist_ok=True)
    path = child_dir(root, analysis_id, "analysis_id")
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError("analysis workspace escapes the server data directory")
    path.mkdir(exist_ok=True)
    return path


def _inside(path: Path, roots: list[Path]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def bound_folders(dataset: str = "", dataset_paths: list[str] | None = None) -> list[dict]:
    """Explicit paths need server-authorized roots; an environment binding authorizes itself."""
    bound = os.environ.get("CELLQC_DATASET") or os.environ.get("AISCIENTIST_DATASET", "")
    roots = [Path(p).expanduser().resolve() for p in os.environ.get("CELLQC_READ_ROOTS", "").split(os.pathsep) if p]
    if bound:
        roots.append(Path(bound).expanduser().resolve())
    requested = ([dataset] if dataset else ([bound] if bound else [])) + (dataset_paths or [])
    if not requested:
        raise ValueError("set CELLQC_DATASET or supply a dataset under CELLQC_READ_ROOTS")
    folders = []
    seen = set()
    for value in requested:
        path = Path(value).expanduser().resolve(strict=True)
        if not _inside(path, roots):
            raise ValueError("dataset is outside CELLQC_READ_ROOTS and the bound dataset")
        if not path.is_dir():
            raise ValueError("CellQC needs a folder with raw AND filtered Cell Ranger matrices")
        if path not in seen:
            folders.append({"name": path.name, "path": str(path)})
            seen.add(path)
    return folders


def input_identity(folders: list[dict]) -> list[dict]:
    """Stat every input entry, rejecting symlink escapes before CellQC stages anything."""
    identities = []
    for folder in folders:
        root = Path(folder["path"])
        entries = []
        for path in [root, *sorted(root.rglob("*"))]:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError("Cell Ranger input contains a symlink outside its dataset folder")
            st = path.stat()
            entries.append([str(path.relative_to(root)), st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino])
        identities.append({"path": str(root), "entries": entries})
    return identities


@contextlib.contextmanager
def lock(path: Path):
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("this analysis already has an active CellQC submission") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def job_settings():
    return jobs.JobSettings.from_env("--cpus-per-task=16 --mem=80G --time=08:00:00")


def task_dir(ws: Path, task_id: str, must_exist=False) -> Path:
    base = ws / "jobs"
    base.mkdir(exist_ok=True)
    dest = child_dir(base, task_id, "task_id", must_exist="state.json" if must_exist else None)
    if dest.is_symlink() or not dest.resolve().is_relative_to(ws):
        raise ValueError("job directory escapes the analysis workspace")
    return dest


def result(ws: Path, task_id: str) -> dict:
    directory = task_dir(ws, task_id, must_exist=True)
    state = jobs.status(job_settings(), directory)
    payload = {
        "analysis_id": ws.name,
        "task_id": task_id,
        **{key: state[key] for key in ("state", "job_id", "error", "note", "elapsed_s") if key in state},
    }
    if (directory / "result.json").exists():
        payload = json.loads((directory / "result.json").read_text()) | payload
    if state.get("state") == "FAILED":
        payload["status"] = "error"
    return payload


def submit(analysis_id: str, dataset: str, dataset_paths: list[str] | None, args: dict, rerun: bool) -> dict:
    folders = bound_folders(dataset, dataset_paths)
    identity = input_identity(folders)
    ws = workspace(analysis_id)
    # A delivery containing the output workspace would change while the job reads it.
    if any(ws.is_relative_to(Path(folder["path"])) or Path(folder["path"]).is_relative_to(ws) for folder in folders):
        raise ValueError("input and CellQC analysis workspace must be separate directories")
    request = {
        "arguments": args,
        "folders": folders,
        "inputs": identity,
        "version": __version__,
        "settings": defaults_source(),
    }
    signature = hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()[:24]
    task_id = "qc-" + signature
    with lock(ws / ".submit.lock"):
        active = ws / "active.json"
        if active.exists():
            active_request = json.loads(active.read_text())
            prior = active_request["task_id"]
            previous = result(ws, prior)
            if previous.get("state") in ACTIVE:
                if active_request.get("signature") == signature and not rerun:
                    return previous
                raise ValueError("another CellQC task is active in this analysis; wait for it to finish")
            if previous.get("state") == "COMPLETED" and active_request.get("signature") == signature and not rerun:
                return previous
        directory = task_dir(ws, task_id)
        if (directory / "state.json").exists() and not rerun:
            previous = result(ws, task_id)
            if (
                previous.get("state") == "COMPLETED"
                and active.exists()
                and json.loads(active.read_text())["task_id"] == task_id
            ):
                return previous
        # Separate attempt folders preserve prior task evidence and avoid stale done/result data.
        if directory.exists():
            from uuid import uuid4

            task_id += "-" + uuid4().hex[:8]
            directory = task_dir(ws, task_id)
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "request.json").write_text(json.dumps(request, indent=2, allow_nan=False))
        active.write_text(json.dumps({"task_id": task_id, "signature": signature}))
        try:
            jobs.submit(
                job_settings(),
                [sys.executable, "-m", "aiscientist_mcp.cellqc.worker", str(directory)],
                directory,
                safe_id(f"cellqc-{analysis_id}"[:60]),
                extra={"task_id": task_id},
            )
        except Exception as exc:
            jobs.write_state(directory, {"state": "FAILED", "error": f"submission failed: {exc}", "task_id": task_id})
            raise
        return result(ws, task_id)
