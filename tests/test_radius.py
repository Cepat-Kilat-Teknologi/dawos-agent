"""Tests for RADIUS diagnostics router endpoints."""

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.models.schemas import (
    RadiusCheckItem,
    RadiusCheckResponse,
    RadiusConfigResponse,
    RadiusConfigServer,
    RadiusStatusResponse,
)

# ---------------------------------------------------------------------------
# GET /api/v1/radius/config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_radius_config_success(client, headers):
    """GET /radius/config returns parsed RADIUS configuration."""
    mock_cfg = {
        "nas_identifier": "accel-ppp",
        "nas_ip_address": "10.0.0.1",
        "gw_ip_address": "10.0.0.1",
        "servers": [{"address": "10.100.0.253", "auth_port": 1812, "acct_port": 1813}],
        "timeout": 5,
        "max_try": 3,
        "acct_timeout": 120,
    }
    with patch(
        "dawos_agent.routers.radius.radius.read_radius_config",
        new_callable=AsyncMock,
        return_value=mock_cfg,
    ):
        resp = await client.get("/api/v1/radius/config", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["nas_identifier"] == "accel-ppp"
    assert len(data["servers"]) == 1
    assert data["servers"][0]["address"] == "10.100.0.253"
    assert data["timeout"] == 5


@pytest.mark.asyncio
async def test_radius_config_error(client, headers):
    """GET /radius/config returns 500 on failure."""
    with patch(
        "dawos_agent.routers.radius.radius.read_radius_config",
        new_callable=AsyncMock,
        side_effect=RuntimeError("file error"),
    ):
        resp = await client.get("/api/v1/radius/config", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_radius_config_no_auth(client, bad_headers):
    """GET /radius/config requires valid API key."""
    resp = await client.get("/api/v1/radius/config", headers=bad_headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/radius/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_radius_status_success(client, headers):
    """GET /radius/status returns live RADIUS stats."""
    mock_status = {
        "servers": [
            {"server_id": "1", "server_address": "10.0.0.1", "state": "active"},
        ],
        "total": 1,
        "active": 1,
        "down": 0,
    }
    with patch(
        "dawos_agent.routers.radius.radius.get_radius_status",
        new_callable=AsyncMock,
        return_value=mock_status,
    ):
        resp = await client.get("/api/v1/radius/status", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["active"] == 1
    assert data["down"] == 0
    assert len(data["servers"]) == 1


@pytest.mark.asyncio
async def test_radius_status_error(client, headers):
    """GET /radius/status returns 500 on accel-cmd failure."""
    with patch(
        "dawos_agent.routers.radius.radius.get_radius_status",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/radius/status", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_radius_status_empty(client, headers):
    """GET /radius/status with no RADIUS servers returns empty."""
    with patch(
        "dawos_agent.routers.radius.radius.get_radius_status",
        new_callable=AsyncMock,
        return_value={"servers": [], "total": 0, "active": 0, "down": 0},
    ):
        resp = await client.get("/api/v1/radius/status", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/v1/radius/check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_radius_check_healthy(client, headers):
    """GET /radius/check returns healthy=True when all servers pass."""
    mock_check = {
        "checks": [
            {
                "address": "10.0.0.1",
                "auth_port": 1812,
                "reachable": True,
                "state": "active",
                "detail": "10.0.0.1:1812 reachable, state active",
            }
        ],
        "total": 1,
        "healthy": True,
    }
    with patch(
        "dawos_agent.routers.radius.radius.check_radius",
        new_callable=AsyncMock,
        return_value=mock_check,
    ):
        resp = await client.get("/api/v1/radius/check", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is True
    assert data["total"] == 1
    assert data["checks"][0]["reachable"] is True


@pytest.mark.asyncio
async def test_radius_check_unhealthy(client, headers):
    """GET /radius/check returns healthy=False when a server fails."""
    mock_check = {
        "checks": [
            {
                "address": "10.0.0.1",
                "auth_port": 1812,
                "reachable": False,
                "state": "down",
                "detail": "10.0.0.1:1812 unreachable",
            }
        ],
        "total": 1,
        "healthy": False,
    }
    with patch(
        "dawos_agent.routers.radius.radius.check_radius",
        new_callable=AsyncMock,
        return_value=mock_check,
    ):
        resp = await client.get("/api/v1/radius/check", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["healthy"] is False


@pytest.mark.asyncio
async def test_radius_check_error(client, headers):
    """GET /radius/check returns 500 on diagnostic failure."""
    with patch(
        "dawos_agent.routers.radius.radius.check_radius",
        new_callable=AsyncMock,
        side_effect=RuntimeError("check failed"),
    ):
        resp = await client.get("/api/v1/radius/check", headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Pydantic model smoke tests
# ---------------------------------------------------------------------------


def test_radius_config_server_defaults():
    """RadiusConfigServer uses standard RADIUS ports as defaults."""
    srv = RadiusConfigServer(address="10.0.0.1")
    assert srv.auth_port == 1812
    assert srv.acct_port == 1813


def test_radius_config_response_defaults():
    """RadiusConfigResponse has sensible empty defaults."""
    resp = RadiusConfigResponse()
    assert resp.nas_identifier == ""
    assert resp.servers == []
    assert resp.timeout == 3
    assert resp.max_try == 3
    assert resp.acct_timeout == 0


def test_radius_status_response_defaults():
    """RadiusStatusResponse defaults to zeros."""
    resp = RadiusStatusResponse()
    assert resp.total == 0
    assert resp.active == 0
    assert resp.down == 0
    assert resp.servers == []


def test_radius_check_item_defaults():
    """RadiusCheckItem defaults."""
    item = RadiusCheckItem(address="10.0.0.1")
    assert item.reachable is False
    assert item.state == "unknown"
    assert item.detail == ""
    assert item.auth_port == 1812


def test_radius_check_response_defaults():
    """RadiusCheckResponse defaults to unhealthy."""
    resp = RadiusCheckResponse()
    assert resp.healthy is False
    assert resp.total == 0
    assert resp.checks == []
