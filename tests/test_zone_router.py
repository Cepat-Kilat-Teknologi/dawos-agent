"""Tests for routers/zone_router.py — Zone firewall endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /zones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_zones(client, headers):
    with patch(
        "dawos_agent.routers.zone_router.zone_firewall.list_zones",
        new_callable=AsyncMock,
        return_value={
            "count": 1,
            "zones": [
                {
                    "name": "filter",
                    "type": "nftables",
                    "description": "nft table filter",
                }
            ],
            "raw_output": "ok",
        },
    ):
        resp = await client.get("/api/v1/zones", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_list_zones_error(client, headers):
    with patch(
        "dawos_agent.routers.zone_router.zone_firewall.list_zones",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/zones", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_list_zones_no_auth(client):
    resp = await client.get("/api/v1/zones")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /zones/{zone}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zone_detail(client, headers):
    with patch(
        "dawos_agent.routers.zone_router.zone_firewall.zone_detail",
        new_callable=AsyncMock,
        return_value={
            "zone": "filter",
            "found": True,
            "rules": [{"chain": "input", "rule": "accept"}],
            "raw_output": "ok",
        },
    ):
        resp = await client.get("/api/v1/zones/filter", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["found"] is True


@pytest.mark.asyncio
async def test_zone_detail_error(client, headers):
    with patch(
        "dawos_agent.routers.zone_router.zone_firewall.zone_detail",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/zones/bad", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /zones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_zone(client, headers):
    with patch(
        "dawos_agent.routers.zone_router.zone_firewall.create_zone",
        new_callable=AsyncMock,
        return_value={"success": True, "message": "Zone 'dmz' created"},
    ):
        resp = await client.post("/api/v1/zones", headers=headers, json={"name": "dmz"})
    assert resp.status_code == 201
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_create_zone_error(client, headers):
    with patch(
        "dawos_agent.routers.zone_router.zone_firewall.create_zone",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post("/api/v1/zones", headers=headers, json={"name": "bad"})
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /zones/{zone}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_zone(client, headers):
    with patch(
        "dawos_agent.routers.zone_router.zone_firewall.delete_zone",
        new_callable=AsyncMock,
        return_value={"success": True, "message": "Zone 'dmz' deleted"},
    ):
        resp = await client.delete("/api/v1/zones/dmz", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_zone_error(client, headers):
    with patch(
        "dawos_agent.routers.zone_router.zone_firewall.delete_zone",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.delete("/api/v1/zones/bad", headers=headers)
    assert resp.status_code == 500
