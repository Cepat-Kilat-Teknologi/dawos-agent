"""Tests for services/scheduler.py — asyncio task scheduler."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import scheduler


@pytest.fixture(autouse=True)
def _reset_scheduler():
    """Clear job store between tests."""
    scheduler._jobs.clear()
    for t in list(scheduler._running_tasks.values()):
        t.cancel()
    scheduler._running_tasks.clear()
    yield
    scheduler._jobs.clear()
    for t in list(scheduler._running_tasks.values()):
        t.cancel()
    scheduler._running_tasks.clear()


# ---------------------------------------------------------------------------
# list / add / remove
# ---------------------------------------------------------------------------


def test_list_jobs_empty():
    assert scheduler.list_jobs() == []


def test_add_job():
    job = scheduler.add_job("test-job", "echo hello", 60, enabled=False)
    assert job["name"] == "test-job"
    assert job["command"] == "echo hello"
    assert job["interval_seconds"] == 60
    assert job["enabled"] is False
    assert job["run_count"] == 0


def test_add_job_duplicate():
    scheduler.add_job("dup", "echo 1", 60, enabled=False)
    with pytest.raises(ValueError, match="already exists"):
        scheduler.add_job("dup", "echo 2", 60, enabled=False)


def test_add_job_enabled_starts_loop():
    with patch.object(scheduler, "_start_loop") as m:
        scheduler.add_job("auto", "echo hi", 60, enabled=True)
    m.assert_called_once_with("auto")


def test_list_jobs_with_entries():
    scheduler.add_job("j1", "echo 1", 30, enabled=False)
    scheduler.add_job("j2", "echo 2", 60, enabled=False)
    jobs = scheduler.list_jobs()
    assert len(jobs) == 2
    assert jobs[0]["name"] == "j1"


def test_remove_job():
    scheduler.add_job("rm-me", "echo bye", 60, enabled=False)
    scheduler.remove_job("rm-me")
    assert scheduler.list_jobs() == []


def test_remove_job_not_found():
    with pytest.raises(KeyError, match="not found"):
        scheduler.remove_job("ghost")


# ---------------------------------------------------------------------------
# run_job
# ---------------------------------------------------------------------------


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_run_job():
    scheduler.add_job("run-test", "echo hello", 60, enabled=False)
    proc = _mock_proc("hello")
    with patch(
        "dawos_agent.services.scheduler.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await scheduler.run_job("run-test")

    assert result["output"] == "hello"
    assert result["returncode"] == 0
    assert scheduler._jobs["run-test"]["run_count"] == 1


@pytest.mark.asyncio
async def test_run_job_not_found():
    with pytest.raises(KeyError, match="not found"):
        await scheduler.run_job("nope")


@pytest.mark.asyncio
async def test_run_job_failure():
    scheduler.add_job("fail-test", "false", 60, enabled=False)
    proc = _mock_proc("err", returncode=1)
    with patch(
        "dawos_agent.services.scheduler.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await scheduler.run_job("fail-test")

    assert result["returncode"] == 1


# ---------------------------------------------------------------------------
# _loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_cancelled():
    """Cover the CancelledError path in _loop."""
    scheduler._jobs["loop-test"] = {
        "name": "loop-test",
        "command": "echo x",
        "interval_seconds": 9999,
        "enabled": True,
        "last_run": None,
        "last_result": None,
        "run_count": 0,
    }
    task = asyncio.ensure_future(scheduler._loop("loop-test"))
    await asyncio.sleep(0)
    task.cancel()
    # _loop catches CancelledError internally, so the task completes cleanly
    await asyncio.sleep(0)
    assert task.done()


@pytest.mark.asyncio
async def test_loop_disabled_exits():
    """Loop should exit when job is disabled."""
    scheduler._jobs["dis-test"] = {
        "name": "dis-test",
        "command": "echo x",
        "interval_seconds": 0,
        "enabled": False,
        "last_run": None,
        "last_result": None,
        "run_count": 0,
    }
    # Loop should exit immediately since enabled=False
    await scheduler._loop("dis-test")


@pytest.mark.asyncio
async def test_loop_survives_execute_error():
    """A transient _execute error must be logged, not kill the loop (DA-M12)."""
    scheduler._jobs["err-loop"] = {
        "name": "err-loop",
        "command": "echo x",
        "interval_seconds": 0,
        "enabled": True,
        "last_run": None,
        "last_result": None,
        "run_count": 0,
    }

    def boom(_name):
        # Disable the job so the loop exits after this failed iteration.
        scheduler._jobs["err-loop"]["enabled"] = False
        raise RuntimeError("boom")

    with patch.object(scheduler, "_execute", new=AsyncMock(side_effect=boom)) as mock:
        await scheduler._loop("err-loop")  # must not raise

    assert mock.call_count == 1


# ---------------------------------------------------------------------------
# _start_loop / _stop_loop
# ---------------------------------------------------------------------------


def test_stop_loop_no_task():
    """Stopping a non-existent loop should be safe."""
    scheduler._stop_loop("nonexistent")  # should not raise


@pytest.mark.asyncio
async def test_start_loop_replaces_existing():
    """Starting a loop for an existing job should cancel the old task."""
    scheduler._jobs["replace"] = {
        "name": "replace",
        "command": "echo x",
        "interval_seconds": 9999,
        "enabled": True,
        "last_run": None,
        "last_result": None,
        "run_count": 0,
    }
    scheduler._start_loop("replace")
    old_task = scheduler._running_tasks["replace"]
    scheduler._start_loop("replace")
    # Let the event loop process the cancellation
    await asyncio.sleep(0)
    assert old_task.cancelled()

    # Clean up
    scheduler._running_tasks["replace"].cancel()


# ---------------------------------------------------------------------------
# _run sudo branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.scheduler.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        await scheduler._run("echo hello", sudo=True)
        args = m.call_args[0]
        assert args[0] == "sudo"


# ---------------------------------------------------------------------------
# _loop executes after sleep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_executes_job():
    """Cover the execute-after-sleep path inside _loop."""
    scheduler._jobs["exec-test"] = {
        "name": "exec-test",
        "command": "echo done",
        "interval_seconds": 0,  # sleep(0) yields immediately
        "enabled": True,
        "last_run": None,
        "last_result": None,
        "run_count": 0,
    }
    proc = _mock_proc("done")
    with patch(
        "dawos_agent.services.scheduler.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        asyncio.ensure_future(scheduler._loop("exec-test"))
        # Let the loop run one iteration
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        # Disable to stop the loop
        scheduler._jobs["exec-test"]["enabled"] = False
        await asyncio.sleep(0)

    assert scheduler._jobs["exec-test"]["run_count"] >= 1


# ---------------------------------------------------------------------------
# _stop_loop with active task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_loop_cancels_task():
    """Cover _stop_loop cancelling an actual running task."""
    scheduler._jobs["stop-me"] = {
        "name": "stop-me",
        "command": "echo x",
        "interval_seconds": 9999,
        "enabled": True,
        "last_run": None,
        "last_result": None,
        "run_count": 0,
    }
    scheduler._start_loop("stop-me")
    await asyncio.sleep(0)
    assert "stop-me" in scheduler._running_tasks
    scheduler._stop_loop("stop-me")
    assert "stop-me" not in scheduler._running_tasks
