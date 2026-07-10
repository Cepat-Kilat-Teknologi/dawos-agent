"""Task scheduler — asyncio-based periodic job management.

Pure-Python asyncio scheduler with REST CRUD and execution history.
Jobs run shell commands at configurable intervals and record their
results in memory for inspection.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# In-memory job store --------------------------------------------------

_jobs: dict[str, dict] = {}
_running_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]


def list_jobs() -> list[dict]:
    """Return all registered jobs with their metadata.

    Returns:
        A list of dicts with ``name``, ``command``, ``interval_seconds``,
        ``enabled``, ``last_run``, ``last_result``, and ``run_count``.
    """
    return [
        {
            "name": j["name"],
            "command": j["command"],
            "interval_seconds": j["interval_seconds"],
            "enabled": j["enabled"],
            "last_run": j.get("last_run"),
            "last_result": j.get("last_result"),
            "run_count": j.get("run_count", 0),
        }
        for j in _jobs.values()
    ]


def add_job(
    name: str,
    command: str,
    interval_seconds: int,
    *,
    enabled: bool = True,
) -> dict:
    """Register a new scheduled job.

    If *enabled*, the job's periodic loop starts immediately.

    Args:
        name: Unique job identifier.
        command: Shell command to execute.
        interval_seconds: Seconds between executions.
        enabled: If True, start the job loop on creation.

    Returns:
        The created job dictionary.

    Raises:
        ValueError: If a job with the same *name* already exists.
    """
    if name in _jobs:
        raise ValueError(f"Job '{name}' already exists")

    job: dict = {
        "name": name,
        "command": command,
        "interval_seconds": interval_seconds,
        "enabled": enabled,
        "last_run": None,
        "last_result": None,
        "run_count": 0,
    }
    _jobs[name] = job

    if enabled:
        _start_loop(name)

    return job


def remove_job(name: str) -> None:
    """Remove a scheduled job and cancel its background loop.

    Args:
        name: The job name to remove.

    Raises:
        KeyError: If the job is not found.
    """
    if name not in _jobs:
        raise KeyError(f"Job '{name}' not found")

    _stop_loop(name)
    del _jobs[name]


async def run_job(name: str) -> dict:
    """Execute a job immediately and return the result.

    Args:
        name: The job name to execute.

    Returns:
        A dictionary with ``output``, ``returncode``, and ``timestamp``.

    Raises:
        KeyError: If the job is not found.
    """
    if name not in _jobs:
        raise KeyError(f"Job '{name}' not found")

    return await _execute(name)


# Internal helpers ------------------------------------------------------


async def _run(cmd: str, *, sudo: bool = False) -> tuple[str, int]:
    """Execute a shell command asynchronously.

    Args:
        cmd: The command string to execute.
        sudo: If True, prefix the command with ``sudo``.

    Returns:
        A tuple of (stdout_text, return_code).
    """
    if sudo:
        cmd = f"sudo {cmd}"
    log.debug("exec: %s", cmd)
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        log.warning("job failed (rc=%d): %s — %s", proc.returncode, cmd, err)
    return out, proc.returncode


async def _execute(name: str) -> dict:
    """Run one job and record the result in its metadata.

    Args:
        name: The job name to execute.

    Returns:
        A dictionary with ``output``, ``returncode``, and ``timestamp``.
    """
    job = _jobs[name]
    out, rc = await _run(job["command"])
    now = datetime.now(timezone.utc).isoformat()
    result = {"output": out, "returncode": rc, "timestamp": now}
    job["last_run"] = now
    job["last_result"] = result
    job["run_count"] = job.get("run_count", 0) + 1
    return result


async def _loop(name: str) -> None:
    """Periodic execution loop for a scheduled job.

    Sleeps for the job's interval, then executes.  Exits when the job
    is removed, disabled, or the task is cancelled.

    Args:
        name: The job name to loop.
    """
    try:
        while name in _jobs and _jobs[name]["enabled"]:
            await asyncio.sleep(_jobs[name]["interval_seconds"])
            if name in _jobs and _jobs[name]["enabled"]:
                try:
                    await _execute(name)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    # A single execution failure must not kill the loop and
                    # leave the job silently stuck as "enabled" (DA-M12).
                    log.error("Scheduled job '%s' execution failed: %s", name, exc)
    except asyncio.CancelledError:
        pass


def _start_loop(name: str) -> None:
    """Start the background asyncio task for a job.

    Args:
        name: The job name whose loop to start.
    """
    if name in _running_tasks:
        _running_tasks[name].cancel()
    _running_tasks[name] = asyncio.ensure_future(_loop(name))


def _stop_loop(name: str) -> None:
    """Cancel the background asyncio task for a job.

    Args:
        name: The job name whose loop to cancel.
    """
    task = _running_tasks.pop(name, None)
    if task is not None:
        task.cancel()
