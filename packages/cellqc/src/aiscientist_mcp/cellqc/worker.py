"""Execute one persisted CellQC request inside its selected executor."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from aiscientist_mcp.common import jobs

from .runtime import input_identity, lock


def execute(directory: Path):
    from .core import run_cellqc

    request = json.loads((directory / "request.json").read_text())
    analysis = directory.parent.parent
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
        (directory / "result.json").write_text(json.dumps(output, indent=2, allow_nan=False))
        if output.get("status") != "ok":
            raise RuntimeError(output.get("error") or output.get("note") or "CellQC did not complete")


def main():
    directory = Path(sys.argv[1]).resolve()
    jobs.record_done(directory, lambda: execute(directory))


if __name__ == "__main__":
    main()
