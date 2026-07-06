"""Tests for routers/lldp_router.py — LLDP endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /lldp/status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lldp_status(client, headers):
    with patch(
        "dawos_agent.routers.lldp_router.lldp.lldp_status",
        new_callable=AsyncMock,
        return_value={"running": True, "raw_output": "config"},
    ):
        resp = await client.get("/api/v1/lldp/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["running"] is True


@pytest.mark.asyncio
async def test_lldp_status_error(client, headers):
    with patch(
        "dawos_agent.routers.lldp_router.lldp.lldp_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/lldp/status", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /lldp/neighbors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lldp_neighbors(client, headers):
    with patch(
        "dawos_agent.routers.lldp_router.lldp.lldp_neighbors",
        new_callable=AsyncMock,
        return_value={
            "count": 1,
            "neighbors": [
                {
                    "local_interface": "eth0",
                    "chassis_name": "sw",
                    "port_id": "p1",
                    "port_description": "",
                    "ttl": "120",
                }
            ],
            "raw_output": "json",
        },
    ):
        resp = await client.get("/api/v1/lldp/neighbors", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_lldp_neighbors_error(client, headers):
    with patch(
        "dawos_agent.routers.lldp_router.lldp.lldp_neighbors",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/lldp/neighbors", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /lldp/neighbors/{name}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lldp_interface(client, headers):
    with patch(
        "dawos_agent.routers.lldp_router.lldp.lldp_interface",
        new_callable=AsyncMock,
        return_value={
            "interface": "eth0",
            "found": True,
            "neighbors": [
                {
                    "local_interface": "eth0",
                    "chassis_name": "sw",
                    "port_id": "p1",
                    "port_description": "",
                }
            ],
            "raw_output": "json",
        },
    ):
        resp = await client.get("/api/v1/lldp/neighbors/eth0", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["found"] is True


@pytest.mark.asyncio
async def test_lldp_interface_error(client, headers):
    with patch(
        "dawos_agent.routers.lldp_router.lldp.lldp_interface",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/lldp/neighbors/eth0", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lldp_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/lldp/status", headers=bad_headers)
    assert resp.status_code == 401
