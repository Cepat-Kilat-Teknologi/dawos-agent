"""Tests for routers/vrrp_router.py — VRRP/HA endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /vrrp/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vrrp_status(client, headers):
    with patch(
        "dawos_agent.routers.vrrp_router.vrrp.vrrp_status",
        new_callable=AsyncMock,
        return_value={
            "active": True,
            "service": "keepalived",
            "groups": [],
            "raw_output": "active",
        },
    ):
        resp = await client.get("/api/v1/vrrp/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["active"] is True


@pytest.mark.asyncio
async def test_vrrp_status_error(client, headers):
    with patch(
        "dawos_agent.routers.vrrp_router.vrrp.vrrp_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/vrrp/status", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_vrrp_status_no_auth(client):
    resp = await client.get("/api/v1/vrrp/status")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /vrrp/groups/{group}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vrrp_group_detail(client, headers):
    with patch(
        "dawos_agent.routers.vrrp_router.vrrp.vrrp_group_detail",
        new_callable=AsyncMock,
        return_value={
            "found": True,
            "group": {
                "name": "WAN",
                "state": "MASTER",
                "priority": 100,
                "vip": "1.2.3.4",
            },
        },
    ):
        resp = await client.get("/api/v1/vrrp/groups/WAN", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["found"] is True


@pytest.mark.asyncio
async def test_vrrp_group_detail_error(client, headers):
    with patch(
        "dawos_agent.routers.vrrp_router.vrrp.vrrp_group_detail",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/vrrp/groups/BAD", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /vrrp/failover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vrrp_failover(client, headers):
    with patch(
        "dawos_agent.routers.vrrp_router.vrrp.vrrp_failover",
        new_callable=AsyncMock,
        return_value={"success": True, "group": "WAN", "message": "triggered"},
    ):
        resp = await client.post(
            "/api/v1/vrrp/failover", headers=headers, json={"group": "WAN"}
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_vrrp_failover_error(client, headers):
    with patch(
        "dawos_agent.routers.vrrp_router.vrrp.vrrp_failover",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/vrrp/failover", headers=headers, json={"group": "BAD"}
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /vrrp/restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vrrp_restart(client, headers):
    with patch(
        "dawos_agent.routers.vrrp_router.vrrp.vrrp_restart",
        new_callable=AsyncMock,
        return_value={"success": True, "group": "", "message": "restarted"},
    ):
        resp = await client.post("/api/v1/vrrp/restart", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_vrrp_restart_error(client, headers):
    with patch(
        "dawos_agent.routers.vrrp_router.vrrp.vrrp_restart",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post("/api/v1/vrrp/restart", headers=headers)
    assert resp.status_code == 500
