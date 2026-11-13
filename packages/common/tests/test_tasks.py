"""Real worker processes exercise task reuse, failures, confinement and async status."""

import os
import time

import pytest
from aiscientist_mcp.common import tasks


@pytest.fixture
def config(tmp_path, monkeypatch):
    worker = tmp_path / "fixture_worker.py"
    worker.write_text("""
import os
import time
from aiscientist_mcp.common.tasks import TaskConfig, worker_main
cfg = TaskConfig("fixture", "fixture_worker", "0.0.1")
def execute(request, workspace):
    if request["operation"] == "abrupt":
        os._exit(7)
    if request["operation"] == "wait":
        while not (workspace / "release").exists():
            time.sleep(0.02)
    if request["operation"] == "fail":
        return {"status": "error", "error": "scientific validation failed"}
    counter = workspace / "counter"
    count = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(count))
    return {"status": "ok", "count": count, "arguments": request["arguments"]}
if __name__ == "__main__":
    worker_main(cfg, execute)
""")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    monkeypatch.setenv("AISCI_DATA_DIR", str(tmp_path / "outputs"))
    monkeypatch.setenv("AISCI_EXECUTOR", "inline")
    return tasks.TaskConfig("fixture", "fixture_worker", "0.0.1")


def test_inline_reuses_only_current_identical_completed_result(config):
    first = tasks.submit(config, "analysis", "count", {"threshold": 3})
    assert first["status"] == "ok" and first["state"] == "COMPLETED" and first["count"] == 1
    assert tasks.submit(config, "analysis", "count", {"threshold": 3}) == first
    changed = tasks.submit(config, "analysis", "count", {"threshold": 4})
    assert changed["count"] == 2 and changed["task_id"] != first["task_id"]
    assert tasks.status(config, "analysis", first["task_id"])["count"] == 1
    assert tasks.submit(config, "analysis", "count", {"threshold": 3})["count"] == 3


def test_input_change_and_rerun_invalidate_cache(config, tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("before")
    first = tasks.submit(config, "analysis", "count", {}, inputs=[str(source)])
    source.write_text("after; different content")
    second = tasks.submit(config, "analysis", "count", {}, inputs=[str(source)])
    third = tasks.submit(config, "analysis", "count", {}, inputs=[str(source)], rerun=True)
    assert [first["count"], second["count"], third["count"]] == [1, 2, 3]


def test_failed_result_is_failed_job(config):
    result = tasks.submit(config, "analysis", "fail", {})
    assert result["state"] == "FAILED" and result["status"] == "error"
    assert "scientific validation failed" in result["error"]


def test_missing_result_is_not_reused_as_success(config):
    first = tasks.submit(config, "analysis", "count", {})
    directory = tasks.task_dir(tasks.workspace(config, "analysis"), first["task_id"])
    (directory / "result.json").unlink()
    assert tasks.status(config, "analysis", first["task_id"])["state"] == "FAILED"
    rerun = tasks.submit(config, "analysis", "count", {})
    assert rerun["status"] == "ok" and rerun["count"] == 2


def test_local_job_reuses_active_request_and_serializes_workspace(config, monkeypatch):
    monkeypatch.setenv("AISCI_EXECUTOR", "local")
    first = tasks.submit(config, "analysis", "wait", {})
    try:
        assert tasks.submit(config, "analysis", "wait", {})["task_id"] == first["task_id"]
        with pytest.raises(ValueError, match="another task"):
            tasks.submit(config, "analysis", "count", {})
    finally:
        (tasks.workspace(config, "analysis") / "release").touch()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = tasks.status(config, "analysis", first["task_id"])
        if result["state"] not in tasks.ACTIVE:
            break
        time.sleep(0.05)
    assert result["state"] == "COMPLETED" and result["status"] == "ok"


def test_workspace_and_input_symlink_escape(config, tmp_path):
    for name in (".", "..", "../escape", "/tmp/out"):
        with pytest.raises(ValueError):
            tasks.workspace(config, name)
    ws = tasks.workspace(config, "ok")
    (ws.parent / "escape").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        tasks.workspace(config, "escape")
    outside = tmp_path / "private.txt"
    outside.write_text("unrelated file")
    (ws / "input").symlink_to(outside)
    with pytest.raises(ValueError, match="read roots"):
        tasks.read_path(str(ws / "input"), [ws])
    with pytest.raises(ValueError, match="unknown task"):
        tasks.status(config, "ok", "missing")


@pytest.mark.parametrize("filename", ["result.json", "state.json", "done.json"])
def test_status_rejects_metadata_symlinks(config, tmp_path, filename):
    first = tasks.submit(config, "analysis", "count", {})
    directory = tasks.task_dir(tasks.workspace(config, "analysis"), first["task_id"])
    outside = tmp_path / "private.json"
    outside.write_text('{"private": "unrelated data"}')
    (directory / filename).unlink()
    (directory / filename).symlink_to(outside)
    with pytest.raises(ValueError, match="regular file"):
        tasks.status(config, "analysis", first["task_id"])
    assert outside.read_text() == '{"private": "unrelated data"}'


def test_submission_rejects_active_metadata_symlink(config, tmp_path):
    ws = tasks.workspace(config, "analysis")
    outside = tmp_path / "private.json"
    outside.write_text("{}")
    (ws / "active.json").symlink_to(outside)
    with pytest.raises(ValueError, match="regular file"):
        tasks.submit(config, "analysis", "count", {})


def test_local_abrupt_exit_releases_workspace(config, monkeypatch):
    monkeypatch.setenv("AISCI_EXECUTOR", "local")
    first = tasks.submit(config, "analysis", "abrupt", {})
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = tasks.status(config, "analysis", first["task_id"])
        if result["state"] not in tasks.ACTIVE:
            break
        time.sleep(0.05)
    assert result["state"] == "FAILED" and result["status"] == "error"
    monkeypatch.setenv("AISCI_EXECUTOR", "inline")
    assert tasks.submit(config, "analysis", "count", {})["state"] == "COMPLETED"
