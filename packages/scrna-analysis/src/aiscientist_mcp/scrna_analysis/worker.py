"""An admitted analysis task, executed inside its Slurm allocation or local process."""

import argparse

from aiscientist_mcp.common.jobs import record_done
from aiscientist_mcp.common.server import quiet

from .runtime import _task_dir, execute, workspace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--task-id", required=True)
    args = parser.parse_args()
    task = _task_dir(workspace(args.analysis_id), args.task_id)
    with quiet():
        record_done(task, lambda: execute(args.analysis_id, args.task_id))


if __name__ == "__main__":
    main()
