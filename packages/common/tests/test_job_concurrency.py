"""Concurrent polling cannot read partial metadata or submit duplicate retries."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from aiscientist_mcp.common import jobs


def test_json_publication_is_atomic(tmp_path, monkeypatch):
    original = {"complete": "previous"}
    jobs.write_json(tmp_path, "result.json", original)
    started, finish = threading.Event(), threading.Event()
    real_dump = json.dump

    def delayed_dump(value, stream, **kwargs):
        stream.write("{")
        stream.flush()
        started.set()
        assert finish.wait(5)
        stream.seek(0)
        stream.truncate()
        real_dump(value, stream, **kwargs)

    monkeypatch.setattr(jobs.json, "dump", delayed_dump)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(jobs.write_json, tmp_path, "result.json", {"complete": "next"})
        try:
            assert started.wait(5)
            assert json.loads((tmp_path / "result.json").read_text()) == original
        finally:
            finish.set()
        future.result()
    assert json.loads((tmp_path / "result.json").read_text()) == {"complete": "next"}
    assert not list(tmp_path.glob(".result.json.*"))


def test_concurrent_preemption_polls_submit_one_retry(tmp_path, monkeypatch):
    cfg = jobs.JobSettings("slurm", "--mem=1G", "--mem=2G", "")
    jobs.write_state(tmp_path, {"executor": "slurm", "job_id": "old", "cmd": ["python", "worker.py"]})
    monkeypatch.setattr(jobs, "_slurm_state", lambda jid: "PREEMPTED" if jid == "old" else "PENDING")
    submissions = []

    def sbatch(command, **kwargs):
        assert command[0] == "sbatch"
        submissions.append(command)
        time.sleep(0.03)
        return SimpleNamespace(stdout="new;cluster\n")

    monkeypatch.setattr(jobs.subprocess, "run", sbatch)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: jobs.status(cfg, tmp_path), range(16)))
    assert len(submissions) == 1
    assert all(result["job_id"] == "new" for result in results)
    assert jobs.read_state(tmp_path)["jobs"] == [{"job_id": "new", "slurm_opts": "--mem=2G"}]


def test_atomic_writer_rejects_symlink_and_nonfinite_value(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("original")
    (tmp_path / "state.json").symlink_to(outside)
    with pytest.raises(ValueError, match="regular file"):
        jobs.write_state(tmp_path, {"changed": True})
    assert outside.read_text() == "original"
    with pytest.raises(ValueError):
        jobs.write_json(tmp_path, "result.json", {"value": float("nan")})
    assert not (tmp_path / "result.json").exists()
    assert not list(tmp_path.glob(".result.json.*"))


@pytest.mark.parametrize("allocation_state,expected", [("CANCELLED", "FAILED"), ("RUNNING", "RUNNING")])
def test_inline_allocation_can_be_checked_from_another_node(tmp_path, monkeypatch, allocation_state, expected):
    cfg = jobs.JobSettings("inline", "", "", "")
    jobs.write_state(
        tmp_path,
        {
            "executor": "inline",
            "state": "RUNNING",
            "allocation_job_id": "12345",
            "proc": {"host": "different-compute-node", "pid": 1, "start": "123"},
        },
    )
    monkeypatch.setattr(jobs, "_slurm_state", lambda jid: allocation_state if jid == "12345" else "UNKNOWN")
    assert jobs.status(cfg, tmp_path)["state"] == expected
