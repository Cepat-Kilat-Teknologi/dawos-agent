"""Tests for service management endpoints — mocked systemctl + accel-cmd."""

from unittest.mock import AsyncMock, patch

import pytest


def _mock_subprocess(stdout=b"", stderr=b"", returncode=0):
    """Helper: create a mock for asyncio.create_subprocess_exec."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_service_status_running(client, headers):
    proc_active = _mock_subprocess(stdout=b"active")
    proc_pid = _mock_subprocess(stdout=b"MainPID=1234")

    call_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return proc_active
        return proc_pid

    with (
        patch(
            "dawos_agent.routers.service.asyncio.create_subprocess_exec",
            side_effect=mock_exec,
        ),
        patch(
            "dawos_agent.routers.service.accel.show_version",
            new_callable=AsyncMock,
            return_value="1.13.0",
        ),
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            return_value={"uptime": "1:00:00"},
        ),
    ):
        resp = await client.get("/api/v1/service/status", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["pid"] == 1234
    assert data["version"] == "1.13.0"


@pytest.mark.asyncio
async def test_service_status_stopped(client, headers):
    proc = _mock_subprocess(stdout=b"inactive", returncode=3)

    with patch(
        "dawos_agent.routers.service.asyncio.create_subprocess_exec", return_value=proc
    ):
        resp = await client.get("/api/v1/service/status", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_service_status_unknown_on_error(client, headers):
    with patch(
        "dawos_agent.routers.service.asyncio.create_subprocess_exec",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/service/status", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "unknown"


@pytest.mark.asyncio
async def test_service_status_running_version_error(client, headers):
    """Version/stat fetch can fail without breaking status."""
    proc_active = _mock_subprocess(stdout=b"active")
    proc_pid = _mock_subprocess(stdout=b"MainPID=0")

    call_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return proc_active
        return proc_pid

    with (
        patch(
            "dawos_agent.routers.service.asyncio.create_subprocess_exec",
            side_effect=mock_exec,
        ),
        patch(
            "dawos_agent.routers.service.accel.show_version",
            new_callable=AsyncMock,
            side_effect=Exception("fail"),
        ),
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            side_effect=Exception("fail"),
        ),
    ):
        resp = await client.get("/api/v1/service/status", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["pid"] is None  # MainPID=0 → None
    assert data["version"] is None


@pytest.mark.asyncio
async def test_service_status_pid_fetch_exception(client, headers):
    """PID subprocess exception should be swallowed (lines 81-82)."""
    proc_active = _mock_subprocess(stdout=b"active")

    call_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return proc_active
        # Second call (PID fetch) raises
        raise OSError("subprocess failed")

    with (
        patch(
            "dawos_agent.routers.service.asyncio.create_subprocess_exec",
            side_effect=mock_exec,
        ),
        patch(
            "dawos_agent.routers.service.accel.show_version",
            new_callable=AsyncMock,
            return_value="1.13.0",
        ),
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            return_value={"uptime": "1:00"},
        ),
    ):
        resp = await client.get("/api/v1/service/status", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["pid"] is None  # PID fetch failed, should be None


@pytest.mark.asyncio
async def test_service_restart(client, headers):
    proc = _mock_subprocess()

    with patch(
        "dawos_agent.routers.service.asyncio.create_subprocess_exec", return_value=proc
    ):
        resp = await client.post("/api/v1/service/restart", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_service_start(client, headers):
    proc = _mock_subprocess()

    with patch(
        "dawos_agent.routers.service.asyncio.create_subprocess_exec", return_value=proc
    ):
        resp = await client.post("/api/v1/service/start", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["action"] == "start"


@pytest.mark.asyncio
async def test_service_stop(client, headers):
    proc = _mock_subprocess()

    with patch(
        "dawos_agent.routers.service.asyncio.create_subprocess_exec", return_value=proc
    ):
        resp = await client.post("/api/v1/service/stop", headers=headers)

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_service_reload(client, headers):
    with patch(
        "dawos_agent.routers.service.accel.reload_config",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post("/api/v1/service/reload", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["message"] == "Config reloaded"


@pytest.mark.asyncio
async def test_service_reload_error(client, headers):
    with patch(
        "dawos_agent.routers.service.accel.reload_config",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.post("/api/v1/service/reload", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_service_restart_fails(client, headers):
    proc = _mock_subprocess(stderr=b"Unit not found", returncode=5)

    with patch(
        "dawos_agent.routers.service.asyncio.create_subprocess_exec", return_value=proc
    ):
        resp = await client.post("/api/v1/service/restart", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_service_action_exception(client, headers):
    with patch(
        "dawos_agent.routers.service.asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError("systemctl"),
    ):
        resp = await client.post("/api/v1/service/start", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_command_allowed(client, headers):
    with patch(
        "dawos_agent.routers.service.accel.run_cmd",
        new_callable=AsyncMock,
        return_value="uptime: 1:00",
    ):
        resp = await client.post(
            "/api/v1/service/command", headers=headers, json={"command": "show stat"}
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_command_show_sessions_with_cols(client, headers):
    with patch(
        "dawos_agent.routers.service.accel.run_cmd",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show sessions username,ip"},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_command_terminate_allowed(client, headers):
    with patch(
        "dawos_agent.routers.service.accel.run_cmd",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "terminate username foo"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_command_shaper_allowed(client, headers):
    with patch(
        "dawos_agent.routers.service.accel.run_cmd",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "shaper change ppp0 10M/20M"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_command_mac_filter_allowed(client, headers):
    with patch(
        "dawos_agent.routers.service.accel.run_cmd",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "pppoe mac-filter show"},
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_command_forbidden(client, headers):
    resp = await client.post(
        "/api/v1/service/command", headers=headers, json={"command": "shutdown hard"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_command_error(client, headers):
    with patch(
        "dawos_agent.routers.service.accel.run_cmd",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.post(
            "/api/v1/service/command", headers=headers, json={"command": "show stat"}
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# Shutdown endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_soft_confirmed(client, headers):
    """POST /shutdown with mode=soft and confirm=true succeeds."""
    with (
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            return_value={"sessions": {"active": 5}},
        ),
        patch(
            "dawos_agent.routers.service.accel.shutdown",
            new_callable=AsyncMock,
            return_value="",
        ) as mock_shutdown,
    ):
        resp = await client.post(
            "/api/v1/service/shutdown",
            headers=headers,
            json={"mode": "soft", "confirm": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["mode"] == "soft"
    assert data["active_sessions"] == 5
    assert "drain" in data["message"]
    mock_shutdown.assert_awaited_once_with("soft")


@pytest.mark.asyncio
async def test_shutdown_hard_confirmed(client, headers):
    """POST /shutdown with mode=hard and confirm=true succeeds."""
    with (
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            return_value={"sessions": {"active": 3}},
        ),
        patch(
            "dawos_agent.routers.service.accel.shutdown",
            new_callable=AsyncMock,
            return_value="",
        ) as mock_shutdown,
    ):
        resp = await client.post(
            "/api/v1/service/shutdown",
            headers=headers,
            json={"mode": "hard", "confirm": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["mode"] == "hard"
    assert data["active_sessions"] == 3
    assert "immediate" in data["message"]
    mock_shutdown.assert_awaited_once_with("hard")


@pytest.mark.asyncio
async def test_shutdown_without_confirm_rejected(client, headers):
    """POST /shutdown without confirm=true returns 400."""
    resp = await client.post(
        "/api/v1/service/shutdown",
        headers=headers,
        json={"mode": "soft", "confirm": False},
    )

    assert resp.status_code == 400
    assert "confirm" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_shutdown_default_mode_is_soft(client, headers):
    """POST /shutdown with only confirm=true defaults to soft mode."""
    with (
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            return_value={"sessions": {"active": 0}},
        ),
        patch(
            "dawos_agent.routers.service.accel.shutdown",
            new_callable=AsyncMock,
            return_value="",
        ) as mock_shutdown,
    ):
        resp = await client.post(
            "/api/v1/service/shutdown",
            headers=headers,
            json={"confirm": True},
        )

    assert resp.status_code == 200
    assert resp.json()["mode"] == "soft"
    mock_shutdown.assert_awaited_once_with("soft")


@pytest.mark.asyncio
async def test_shutdown_accel_cmd_failure(client, headers):
    """POST /shutdown returns 500 when accel-cmd fails."""
    with (
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            return_value={"sessions": {"active": 2}},
        ),
        patch(
            "dawos_agent.routers.service.accel.shutdown",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ),
    ):
        resp = await client.post(
            "/api/v1/service/shutdown",
            headers=headers,
            json={"mode": "soft", "confirm": True},
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_shutdown_stat_failure_still_proceeds(client, headers):
    """Session count failure should not block shutdown execution."""
    with (
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            side_effect=RuntimeError("stat failed"),
        ),
        patch(
            "dawos_agent.routers.service.accel.shutdown",
            new_callable=AsyncMock,
            return_value="",
        ),
    ):
        resp = await client.post(
            "/api/v1/service/shutdown",
            headers=headers,
            json={"mode": "soft", "confirm": True},
        )

    assert resp.status_code == 200
    assert resp.json()["active_sessions"] == 0


@pytest.mark.asyncio
async def test_shutdown_cancel(client, headers):
    """POST /shutdown/cancel succeeds and resumes normal operation."""
    with (
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            return_value={"sessions": {"active": 7}},
        ),
        patch(
            "dawos_agent.routers.service.accel.shutdown_cancel",
            new_callable=AsyncMock,
            return_value="",
        ) as mock_cancel,
    ):
        resp = await client.post(
            "/api/v1/service/shutdown/cancel",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["mode"] == "cancel"
    assert data["active_sessions"] == 7
    assert "cancelled" in data["message"].lower()
    mock_cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_cancel_failure(client, headers):
    """POST /shutdown/cancel returns 500 when accel-cmd fails."""
    with (
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            return_value={"sessions": {"active": 1}},
        ),
        patch(
            "dawos_agent.routers.service.accel.shutdown_cancel",
            new_callable=AsyncMock,
            side_effect=RuntimeError("not in shutdown"),
        ),
    ):
        resp = await client.post(
            "/api/v1/service/shutdown/cancel",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_shutdown_cancel_stat_failure(client, headers):
    """Stat failure during cancel should not block the cancel itself."""
    with (
        patch(
            "dawos_agent.routers.service.accel.show_stat",
            new_callable=AsyncMock,
            side_effect=RuntimeError("stat failed"),
        ),
        patch(
            "dawos_agent.routers.service.accel.shutdown_cancel",
            new_callable=AsyncMock,
            return_value="",
        ),
    ):
        resp = await client.post(
            "/api/v1/service/shutdown/cancel",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["active_sessions"] == 0
