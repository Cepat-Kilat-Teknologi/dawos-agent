"""Tests for config router endpoints — mocked filesystem."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_config(client, headers):
    with patch(
        "dawos_agent.routers.config_router.config_manager.read_config",
        return_value=("[ppp]\n", datetime(2025, 1, 1)),
    ):
        resp = await client.get("/api/v1/config", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "[ppp]" in data["content"]
    assert data["last_modified"] is not None


@pytest.mark.asyncio
async def test_get_config_not_found(client, headers):
    with patch(
        "dawos_agent.routers.config_router.config_manager.read_config",
        side_effect=FileNotFoundError("not found"),
    ):
        resp = await client.get("/api/v1/config", headers=headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_config_error(client, headers):
    with patch(
        "dawos_agent.routers.config_router.config_manager.read_config",
        side_effect=PermissionError("denied"),
    ):
        resp = await client.get("/api/v1/config", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_update_config_no_restart(client, headers):
    with patch(
        "dawos_agent.routers.config_router.config_manager.write_config",
        return_value="/etc/accel-ppp.d/bak",
    ):
        resp = await client.put(
            "/api/v1/config",
            headers=headers,
            json={
                "content": "[ppp]\nnew=val",
                "restart_service": False,
                "backup": True,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "updated" in data["message"].lower()
    assert data["backup_path"] == "/etc/accel-ppp.d/bak"


@pytest.mark.asyncio
async def test_update_config_with_restart(client, headers):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b""))
    proc.returncode = 0

    with (
        patch(
            "dawos_agent.routers.config_router.config_manager.write_config",
            return_value=None,
        ),
        patch(
            "dawos_agent.routers.config_router.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
    ):
        resp = await client.put(
            "/api/v1/config",
            headers=headers,
            json={"content": "[ppp]\n", "restart_service": True, "backup": False},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "restarted" in data["message"].lower()


@pytest.mark.asyncio
async def test_update_config_restart_fails(client, headers):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"", b"unit not found"))
    proc.returncode = 1

    with (
        patch(
            "dawos_agent.routers.config_router.config_manager.write_config",
            return_value="/bak",
        ),
        patch(
            "dawos_agent.routers.config_router.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
    ):
        resp = await client.put(
            "/api/v1/config",
            headers=headers,
            json={"content": "[ppp]\n", "restart_service": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "restart failed" in data["message"].lower()


@pytest.mark.asyncio
async def test_update_config_write_error(client, headers):
    with patch(
        "dawos_agent.routers.config_router.config_manager.write_config",
        side_effect=PermissionError("denied"),
    ):
        resp = await client.put(
            "/api/v1/config",
            headers=headers,
            json={"content": "x"},
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_list_backups(client, headers):
    mock_backups = [
        {
            "path": "/etc/accel-ppp.d/a.bak",
            "name": "a.bak",
            "size": 100,
            "created": "2025-01-01T00:00:00",
        },
    ]
    with patch(
        "dawos_agent.routers.config_router.config_manager.list_backups",
        return_value=mock_backups,
    ):
        resp = await client.get("/api/v1/config/backups", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "a.bak"
