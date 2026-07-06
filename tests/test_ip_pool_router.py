"""Tests for routers/ip_pool_router.py — IP pool endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /ip-pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pools(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.list_pools",
        return_value=[{"name": "customers", "range": "10.0.0.0/24"}],
    ):
        resp = await client.get("/api/v1/ip-pool", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_list_pools_not_found(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.list_pools",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.get("/api/v1/ip-pool", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_pools_error(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.list_pools",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/ip-pool", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /ip-pool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_pool(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.add_pool",
        return_value="Added pool vip",
    ), patch(
        "dawos_agent.routers.ip_pool_router.reload_config",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            "/api/v1/ip-pool",
            json={"name": "vip", "ip_range": "172.16.0.0/24"},
            headers=headers,
        )
    assert resp.status_code == 201
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_add_pool_duplicate(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.add_pool",
        side_effect=ValueError("already exists"),
    ):
        resp = await client.post(
            "/api/v1/ip-pool",
            json={"name": "dup", "ip_range": "10.0.0.0/24"},
            headers=headers,
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_pool_reload_failure(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.add_pool",
        return_value="Added",
    ), patch(
        "dawos_agent.routers.ip_pool_router.reload_config",
        new_callable=AsyncMock,
        side_effect=Exception("reload fail"),
    ):
        resp = await client.post(
            "/api/v1/ip-pool",
            json={"name": "new", "ip_range": "10.1.0.0/24"},
            headers=headers,
        )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_add_pool_not_found(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.add_pool",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.post(
            "/api/v1/ip-pool",
            json={"name": "x", "ip_range": "10.0.0.0/24"},
            headers=headers,
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_pool_error(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.add_pool",
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/ip-pool",
            json={"name": "x", "ip_range": "10.0.0.0/24"},
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /ip-pool/{name}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_pool(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.remove_pool",
        return_value="Removed",
    ), patch(
        "dawos_agent.routers.ip_pool_router.reload_config",
        new_callable=AsyncMock,
    ):
        resp = await client.delete("/api/v1/ip-pool/customers", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_remove_pool_not_found(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.remove_pool",
        side_effect=ValueError("not found"),
    ):
        resp = await client.delete("/api/v1/ip-pool/ghost", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_pool_reload_failure(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.remove_pool",
        return_value="Removed",
    ), patch(
        "dawos_agent.routers.ip_pool_router.reload_config",
        new_callable=AsyncMock,
        side_effect=Exception("reload fail"),
    ):
        resp = await client.delete("/api/v1/ip-pool/old", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_remove_pool_file_not_found(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.remove_pool",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.delete("/api/v1/ip-pool/x", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_pool_error(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.remove_pool",
        side_effect=Exception("fail"),
    ):
        resp = await client.delete("/api/v1/ip-pool/x", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /ip-pool/usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_usage(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.pool_usage",
        new_callable=AsyncMock,
        return_value={"used": "100", "total": "500", "available": "400"},
    ):
        resp = await client.get("/api/v1/ip-pool/usage", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["used"] == "100"


@pytest.mark.asyncio
async def test_pool_usage_error(client, headers):
    with patch(
        "dawos_agent.routers.ip_pool_router.ip_pool.pool_usage",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/ip-pool/usage", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ip_pool_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/ip-pool", headers=bad_headers)
    assert resp.status_code == 401
