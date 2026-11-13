"""Execute one persisted CellQC request inside its selected executor."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from aiscientist_mcp.common import jobs

from .runtime import input_identity, lock, task_dir, workspace


def checked_directory(directory: Path) -> Path:
    directory = directory.absolute()
    analysis = workspace(directory.parent.parent.name)
    if directory != task_dir(analysis, directory.name) or not directory.is_dir():
        raise ValueError("worker request is outside its configured workspace")
    return directory


def execute(directory: Path):
    from .core import run_cellqc

    directory = checked_directory(directory)
    request = json.loads(jobs.managed_file(directory, "request.json").read_text())
    analysis = directory.parent.parent
    if request["analysis_id"] != analysis.name:
        raise ValueError("worker request does not belong to this analysis")
    ws = directory / "output"
    with lock(analysis / ".work.lock"):
        if input_identity(request["folders"]) != request["inputs"]:
            raise ValueError("input delivery changed after submission; submit a new task")
        ctx = SimpleNamespace(workspace=ws, decisions={"input_folders": request["folders"]})
        output = run_cellqc(request["arguments"], ctx)
        output["settings_source"] = request["settings"]
        if output.get("status") == "ok":
            output["checkpoint_path"] = str(ws / "work" / output["checkpoint"])
            output["artifact_root"] = str(ws / "artifacts")
            output["result_directory"] = str(ws / "result/cellqc")
        jobs.write_json(directory, "result.json", output)
        if output.get("status") != "ok":
            raise RuntimeError(output.get("error") or output.get("note") or "CellQC did not complete")


def main():
    directory = checked_directory(Path(sys.argv[1]))
    jobs.record_done(directory, lambda: execute(directory))


if __name__ == "__main__":
    main()
