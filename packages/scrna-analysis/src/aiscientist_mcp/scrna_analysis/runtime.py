"""Confined analysis workspaces and common Slurm/local/inline jobs.

The scientific functions have no dependency on the AiScientist application. Their
small context contains only the admitted dataset and this analysis's workspace.
"""

import contextlib
import fcntl
import hashlib
import importlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

from aiscientist_mcp.common import jobs
from aiscientist_mcp.common.paths import child_dir, safe_id
from jsonschema import Draft202012Validator

from . import SERVER_NAME, __version__

SPECS = json.loads(Path(__file__).with_name("tool_specs.json").read_text())
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE"}
CHAINS = {
    "run_scanpy_qc": (),
    "run_clustering": ("adata_qc.h5ad",),
    "run_de": ("adata_clustered.h5ad", "adata_qc.h5ad"),
    "run_depth_matched_de": ("adata_clustered.h5ad", "adata_qc.h5ad"),
    "run_doublet_detection": ("adata_qc.h5ad",),
    "run_integration": ("adata_qc.h5ad",),
    "run_pseudobulk_de": ("adata_qc.h5ad", "adata_annotated.h5ad", "adata_de.h5ad", "adata_clustered.h5ad"),
    "run_composition": ("adata_annotated.h5ad", "adata_de.h5ad", "adata_clustered.h5ad", "adata_qc.h5ad"),
    "run_marker_annotation": ("adata_de.h5ad", "adata_clustered.h5ad"),
}


def _json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False))
    tmp.replace(path)


def workspace(analysis_id):
    base = Path(os.environ.get("AISCI_DATA_DIR", "./data")).expanduser().resolve()
    root = base / SERVER_NAME
    if root.is_symlink() or root.resolve().parent != base:
        raise ValueError("server workspace escapes the configured data directory")
    root.mkdir(parents=True, exist_ok=True)
    path = child_dir(root, analysis_id, "analysis_id")
    if path.is_symlink() or path.resolve().parent != root.resolve():
        raise ValueError("analysis workspace escapes the configured data directory")
    path.mkdir(exist_ok=True)
    # An existing symlink could redirect a fixed checkpoint, figure or state path.
    if any(p.is_symlink() for p in path.rglob("*")):
        raise ValueError("analysis workspace contains a symlink; use regular files")
    for name in ("work", "artifacts", "jobs"):
        (path / name).mkdir(exist_ok=True)
    return path


@contextlib.contextmanager
def lock(path):
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("this analysis is busy; poll its active task before submitting another") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def bind_dataset(ws, supplied):
    binding = ws / "dataset.json"
    previous = json.loads(binding.read_text()).get("path", "") if binding.exists() else ""
    configured = os.environ.get("SCRNA_DATASET") or os.environ.get("AISCIENTIST_DATASET", "")
    text = supplied or previous or configured
    if not text:
        return ""
    path = Path(text).expanduser().resolve()
    allowed = [Path(p).expanduser().resolve() for p in os.environ.get("SCRNA_READ_ROOTS", "").split(os.pathsep) if p]
    if configured:
        allowed.append(Path(configured).expanduser().resolve())
    if not any(path == root or (root.is_dir() and root in path.parents) for root in allowed):
        raise ValueError("dataset is outside SCRNA_READ_ROOTS and is not the configured SCRNA_DATASET")
    if not path.exists():
        raise ValueError("dataset does not exist")
    if previous and previous != str(path):
        raise ValueError("analysis_id is already bound to another dataset; use a new analysis_id")
    _json(binding, {"path": str(path)})
    return str(path)


def _identity(path):
    path = Path(path)
    if not path.exists():
        return {"path": str(path), "missing": True}
    if path.is_dir():
        return {"path": str(path), "files": [_identity(p) for p in sorted(path.rglob("*")) if p.is_file()]}
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _handoff_checkpoints(ws):
    """Read-only files from an operator-configured shared checkpoint directory."""
    configured = os.environ.get("SCRNA_CHECKPOINT_ROOT", "")
    if not configured:
        return []
    root = Path(configured).expanduser()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("SCRNA_CHECKPOINT_ROOT must be a regular directory")
    root = root.resolve()
    manifest = ws / "checkpoint_imports.json"
    imported = json.loads(manifest.read_text()) if manifest.exists() else {}
    for name, original in imported.items():
        source = root / name
        if source.is_symlink() or _identity(source) != original:
            raise ValueError("upstream checkpoint changed after import; use a new analysis_id to avoid mixing analyses")
    paths = []
    for path in sorted(root.glob("adata_*.h5ad")):
        if not re.fullmatch(r"adata_[A-Za-z0-9_.-]+\.h5ad", path.name):
            continue
        if path.is_symlink() or path.resolve().parent != root or not path.is_file():
            raise ValueError("checkpoint handoff must contain regular files inside its configured root")
        if not (ws / "work" / path.name).exists():
            paths.append(path)
    return paths


def _input_identity(ws, name, args, dataset):
    from ._lib.scrna import _genesets_dir, _run_files

    ctx = SimpleNamespace(workspace=ws, decisions={"dataset_path": dataset})
    explicit = str(args.get("input") or "").strip()
    handoffs = _handoff_checkpoints(ws)
    paths = []
    if explicit:
        suffixes = (".rnk",) if name == "run_gsea_prerank" else (".h5ad",)
        paths, why = _run_files(ctx, explicit, suffixes, pattern_ok=name == "run_gsea_prerank")
        if why:
            requested = Path(explicit)
            target = requested if requested.is_absolute() else ws / requested
            available = [p for p in handoffs if target == ws / "work" / p.name]
            if len(available) != 1:
                raise ValueError(why)
            paths = available
    elif name == "run_scanpy_qc":
        if not dataset:
            raise ValueError("run_scanpy_qc needs a dataset; configure SCRNA_DATASET or pass an admitted dataset")
        paths = [Path(dataset)]
    elif name in CHAINS:
        candidates = [ws / "work" / p for p in CHAINS[name]]
        paths = [p for p in candidates if p.exists()]
        if name != "run_pseudobulk_de":
            paths = paths[:1]
    elif name == "run_gsea_prerank":
        paths = sorted((ws / "artifacts/tables").glob("rank_*.rnk"))
    if name == "run_enrichment":
        paths += sorted((ws / "artifacts/tables").glob("de_*"))
    if name in {"run_enrichment", "run_gsea_prerank"}:
        paths += sorted(_genesets_dir().glob("*.gmt"))
    paths += [p for p in handoffs if p not in paths]
    return [_identity(p) for p in paths]


def _validate(name, args):
    if name not in SPECS:
        raise ValueError("unknown single-cell tool")
    Draft202012Validator(SPECS[name]["inputSchema"]).validate(args)
    # These are names, never paths; legacy algorithms interpolate them in file names.
    for value in [args.get("groupby", ""), *(args.get("gene_sets") or [])]:
        if any(ch in str(value) for ch in ("/", "\\", "\x00")) or str(value) in {".", ".."}:
            raise ValueError("groupby and gene_sets must be names, not paths")
    json.dumps(args, allow_nan=False)


def _task_dir(ws, task_id):
    path = child_dir(ws / "jobs", task_id, "task_id", must_exist="request.json")
    if path.is_symlink() or path.resolve().parent != (ws / "jobs").resolve():
        raise ValueError("task path escapes this analysis")
    return path


def _outputs(ws):
    return [
        _identity(path)
        for folder in ("work", "artifacts")
        for path in sorted((ws / folder).rglob("*"))
        if path.is_file()
    ]


def _cache_valid(task):
    saved = task / "outputs.json"
    if not saved.exists():
        return False
    return all(item == _identity(item["path"]) for item in json.loads(saved.read_text()))


def _response(ws, analysis_id, task_id):
    path = _task_dir(ws, task_id)
    state = jobs.status(jobs.JobSettings.from_env(), path)
    result_path = path / "result.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else {}
    if state.get("state") == "COMPLETED" and not result_path.exists():
        state = state | {"state": "FAILED", "error": "job completed without result.json"}
    # Identity cannot be overwritten by a domain result.
    return (
        result
        | {
            "analysis_id": analysis_id,
            "task_id": task_id,
            "job_id": state.get("job_id", ""),
            "state": state.get("state", "UNKNOWN"),
        }
        | {key: state[key] for key in ("error", "note", "elapsed_s") if key in state}
    )


def submit(name, args, analysis_id="default", dataset="", rerun=False):
    """Submit once per effective input and arguments; inline returns original result fields."""
    _validate(name, args)
    ws = workspace(analysis_id)
    with lock(ws / ".submit.lock"):
        bound = bind_dataset(ws, dataset)
        identity = _input_identity(ws, name, args, bound)
        request = {
            "version": __version__,
            "tool": name,
            "args": args,
            "dataset": bound,
            "inputs": identity,
            "genesets": os.environ.get("SCRNA_GENESETS_DIR") or os.environ.get("AISCIENTIST_GENESETS_DIR", ""),
            "checkpoint_root": os.environ.get("SCRNA_CHECKPOINT_ROOT", ""),
        }
        task_id = hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest()[:32]
        active = ws / "active.json"
        if active.exists():
            active_id = json.loads(active.read_text())["task_id"]
            current = _response(ws, analysis_id, active_id)
            if current["state"] not in TERMINAL:
                if task_id == active_id and not rerun:
                    return current
                raise ValueError(f"analysis {analysis_id} has active task {active_id}; poll scrna_job_status")
        task = child_dir(ws / "jobs", task_id, "task_id")
        if (task / "request.json").exists() and not rerun:
            old = _response(ws, analysis_id, task_id)
            if old["state"] == "COMPLETED" and _cache_valid(task):
                return old
        task.mkdir(exist_ok=True)
        _json(task / "request.json", request | {"analysis_id": analysis_id})
        (task / "result.json").unlink(missing_ok=True)
        _json(active, {"task_id": task_id})
        try:
            executor = jobs.JobSettings.from_env()
            python = os.environ.get("AISCI_JOB_PYTHON") or ("python" if executor.prefix else sys.executable)
            jobs.submit(
                executor,
                [
                    python,
                    "-m",
                    "aiscientist_mcp.scrna_analysis.worker",
                    "--analysis-id",
                    analysis_id,
                    "--task-id",
                    task_id,
                ],
                task,
                f"scrna_{name}_{task_id[:8]}",
            )
        except Exception:
            # No orphaned active record should block every later submission.
            _json(task / "done.json", {"state": "FAILED", "error": "executor could not submit the job"})
            raise
        result = _response(ws, analysis_id, task_id)
        if result["state"] == "FAILED":
            raise ValueError(
                f"scrna task {task_id} failed: {result.get('error') or result.get('note') or result.get('status')}; "
                f"poll scrna_job_status with analysis_id={analysis_id!r} for its result"
            )
        return result


def status(analysis_id, task_id):
    safe_id(task_id, "task_id")
    ws = workspace(analysis_id)
    with lock(ws / ".submit.lock"):
        return _response(ws, analysis_id, task_id)


def execute(analysis_id, task_id):
    ws = workspace(analysis_id)
    task = _task_dir(ws, task_id)
    request = json.loads((task / "request.json").read_text())
    with lock(ws / ".analysis.lock"):
        name, args = request["tool"], request["args"]
        _validate(name, args)
        dataset = bind_dataset(ws, request["dataset"])
        if request["inputs"] != _input_identity(ws, name, args, dataset):
            raise ValueError("input changed after submission; submit again against the current input")
        manifest = ws / "checkpoint_imports.json"
        imported = json.loads(manifest.read_text()) if manifest.exists() else {}
        for source in _handoff_checkpoints(ws):
            shutil.copy2(source, ws / "work" / source.name)
            imported[source.name] = _identity(source)
        if imported:
            _json(manifest, imported)
        module = importlib.import_module(f"aiscientist_mcp.scrna_analysis.{name}.tool")
        ctx = SimpleNamespace(workspace=ws, decisions={"dataset_path": dataset})
        result = getattr(module, name)(args, ctx)
        checkpoint = str(result.get("checkpoint") or "")
        checkpoint_name = Path(checkpoint)
        candidate = (
            ws / checkpoint_name
            if checkpoint_name.parts and checkpoint_name.parts[0] == "work"
            else ws / "work" / checkpoint_name
        )
        if not checkpoint:
            candidates = sorted((ws / "work").glob("adata_*.h5ad"), key=lambda path: path.stat().st_mtime_ns)
            candidate = candidates[-1] if candidates else ws / "work"
        checkpoint_path = ""
        if candidate.is_file() and candidate.resolve().is_relative_to(ws.resolve()):
            checkpoint_path = str(candidate.resolve())
        result = result | {"artifact_root": str(ws / "artifacts"), "checkpoint_path": checkpoint_path}
        _json(task / "result.json", result)
        if result.get("status") != "ok":
            raise ValueError(result.get("error") or result.get("note") or result.get("status", "analysis failed"))
        _json(task / "outputs.json", _outputs(ws))
