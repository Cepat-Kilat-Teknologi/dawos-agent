"""Tests for routers/fw_groups_router.py — Firewall groups endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /firewall/groups
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_groups(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.list_groups",
        new_callable=AsyncMock,
        return_value={
            "count": 1,
            "groups": [{"name": "ips", "type": "ipv4_addr", "elements": []}],
            "raw_output": "ok",
        },
    ):
        resp = await client.get("/api/v1/firewall/groups", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_list_groups_error(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.list_groups",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/firewall/groups", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_list_groups_no_auth(client):
    resp = await client.get("/api/v1/firewall/groups")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /firewall/groups
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_group(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.create_group",
        new_callable=AsyncMock,
        return_value={
            "success": True,
            "message": "created",
            "name": "ips",
            "type": "address",
        },
    ):
        resp = await client.post(
            "/api/v1/firewall/groups",
            headers=headers,
            json={"name": "ips", "group_type": "address"},
        )
    assert resp.status_code == 201
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_create_group_invalid_type(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.create_group",
        new_callable=AsyncMock,
        side_effect=ValueError("Invalid group type"),
    ):
        resp = await client.post(
            "/api/v1/firewall/groups",
            headers=headers,
            json={"name": "bad", "group_type": "invalid"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_group_error(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.create_group",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/firewall/groups",
            headers=headers,
            json={"name": "bad", "group_type": "address"},
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /firewall/groups/{name}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_group(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.delete_group",
        new_callable=AsyncMock,
        return_value={"success": True, "message": "deleted"},
    ):
        resp = await client.delete("/api/v1/firewall/groups/ips", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_group_error(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.delete_group",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.delete("/api/v1/firewall/groups/bad", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /firewall/groups/{name}/members
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_members(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.add_members",
        new_callable=AsyncMock,
        return_value={"success": True, "message": "added"},
    ):
        resp = await client.post(
            "/api/v1/firewall/groups/ips/members",
            headers=headers,
            json={"elements": ["10.0.0.1"]},
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_add_members_error(client, headers):
    with patch(
        "dawos_agent.routers.fw_groups_router.firewall_groups.add_members",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/firewall/groups/bad/members",
            headers=headers,
            json={"elements": ["10.0.0.1"]},
        )
    assert resp.status_code == 500
