"""Tests for routers/dhcp_router.py — DHCP endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /dhcp/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dhcp_status(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.dhcp_status",
        new_callable=AsyncMock,
        return_value={
            "active": True,
            "service": "dnsmasq",
            "lease_count": 5,
            "raw_output": "active",
        },
    ):
        resp = await client.get("/api/v1/dhcp/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["active"] is True
    assert resp.json()["service"] == "dnsmasq"


@pytest.mark.asyncio
async def test_dhcp_status_error(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.dhcp_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/dhcp/status", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_dhcp_status_no_auth(client):
    resp = await client.get("/api/v1/dhcp/status")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /dhcp/leases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dhcp_leases(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.dhcp_leases",
        new_callable=AsyncMock,
        return_value={
            "count": 2,
            "leases": [
                {
                    "expires": 100,
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "ip": "10.0.0.5",
                    "hostname": "pc",
                    "client_id": "01:aa",
                },
            ],
            "raw_output": "raw",
        },
    ):
        resp = await client.get("/api/v1/dhcp/leases", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


@pytest.mark.asyncio
async def test_dhcp_leases_error(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.dhcp_leases",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/dhcp/leases", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /dhcp/relay/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relay_status(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.relay_status",
        new_callable=AsyncMock,
        return_value={
            "active": True,
            "service": "dhcrelay",
            "config": {"interface": "eth0", "servers": ["10.0.0.1"]},
            "raw_output": "active",
        },
    ):
        resp = await client.get("/api/v1/dhcp/relay/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["active"] is True


@pytest.mark.asyncio
async def test_relay_status_error(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.relay_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/dhcp/relay/status", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /dhcp/restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dhcp_restart(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.dhcp_restart",
        new_callable=AsyncMock,
        return_value={"success": True, "message": "DHCP server restarted"},
    ):
        resp = await client.post("/api/v1/dhcp/restart", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_dhcp_restart_error(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.dhcp_restart",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post("/api/v1/dhcp/restart", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /dhcp/relay/restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relay_restart(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.relay_restart",
        new_callable=AsyncMock,
        return_value={"success": True, "message": "DHCP relay restarted"},
    ):
        resp = await client.post("/api/v1/dhcp/relay/restart", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_relay_restart_error(client, headers):
    with patch(
        "dawos_agent.routers.dhcp_router.dhcp.relay_restart",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post("/api/v1/dhcp/relay/restart", headers=headers)
    assert resp.status_code == 500
