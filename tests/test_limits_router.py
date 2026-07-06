"""Tests for routers/limits_router.py — connection limits endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /limits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_limits(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.get_limits",
        return_value={"max_sessions": 500, "max_starting": 50, "session_timeout": 3600},
    ):
        resp = await client.get("/api/v1/limits", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["max_sessions"] == 500


@pytest.mark.asyncio
async def test_get_limits_not_found(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.get_limits",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.get("/api/v1/limits", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_limits_error(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.get_limits",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/limits", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# PUT /limits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_limits(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.set_limits",
        return_value="ok",
    ), patch(
        "dawos_agent.routers.limits_router.reload_config",
        new_callable=AsyncMock,
    ), patch(
        "dawos_agent.routers.limits_router.connection_limits.get_limits",
        return_value={"max_sessions": 1000, "max_starting": 100, "session_timeout": 0},
    ):
        resp = await client.put(
            "/api/v1/limits",
            json={"max_sessions": 1000, "max_starting": 100},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["max_sessions"] == 1000


@pytest.mark.asyncio
async def test_set_limits_reload_failure(client, headers):
    """Cover the reload failure warning branch."""
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.set_limits",
        return_value="ok",
    ), patch(
        "dawos_agent.routers.limits_router.reload_config",
        new_callable=AsyncMock,
        side_effect=Exception("reload fail"),
    ), patch(
        "dawos_agent.routers.limits_router.connection_limits.get_limits",
        return_value={"max_sessions": 1000, "max_starting": 0, "session_timeout": 0},
    ):
        resp = await client.put(
            "/api/v1/limits",
            json={"max_sessions": 1000},
            headers=headers,
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_set_limits_not_found(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.set_limits",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.put(
            "/api/v1/limits",
            json={"max_sessions": 100},
            headers=headers,
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_limits_error(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.set_limits",
        side_effect=Exception("fail"),
    ):
        resp = await client.put(
            "/api/v1/limits",
            json={"max_sessions": 100},
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /limits/interface/{name}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_interface_limit(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.get_interface_limit",
        return_value={"interface": "eth0", "padi_limit": 50, "found": True},
    ):
        resp = await client.get("/api/v1/limits/interface/eth0", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["found"] is True


@pytest.mark.asyncio
async def test_get_interface_limit_not_found(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.get_interface_limit",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.get("/api/v1/limits/interface/eth0", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_interface_limit_error(client, headers):
    with patch(
        "dawos_agent.routers.limits_router.connection_limits.get_interface_limit",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/limits/interface/eth0", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limits_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/limits", headers=bad_headers)
    assert resp.status_code == 401
