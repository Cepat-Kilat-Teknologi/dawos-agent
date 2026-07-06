"""Tests for routers/routing.py — BGP/OSPF endpoint tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# BGP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bgp_status(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.bgp_summary",
        new_callable=AsyncMock,
        return_value={
            "configured": True,
            "router_id": "10.0.0.1",
            "local_as": "65000",
            "neighbors": [],
            "total_prefixes": 0,
            "raw_output": "BGP summary",
        },
    ):
        resp = await client.get(
            "/api/v1/routing/bgp/status",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["router_id"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_bgp_status_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.bgp_summary",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/routing/bgp/status",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_bgp_routes(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.bgp_routes",
        new_callable=AsyncMock,
        return_value={"count": 5, "raw_output": "routes"},
    ):
        resp = await client.get(
            "/api/v1/routing/bgp/routes",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["count"] == 5


@pytest.mark.asyncio
async def test_bgp_routes_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.bgp_routes",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/routing/bgp/routes",
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# OSPF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ospf_status(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.ospf_status",
        new_callable=AsyncMock,
        return_value={
            "configured": True,
            "router_id": "10.0.0.1",
            "neighbors": [],
            "raw_output": "OSPF status",
        },
    ):
        resp = await client.get(
            "/api/v1/routing/ospf/status",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["configured"] is True


@pytest.mark.asyncio
async def test_ospf_status_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.ospf_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/routing/ospf/status",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_ospf_neighbors(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.ospf_neighbors",
        new_callable=AsyncMock,
        return_value={
            "configured": True,
            "neighbors": [
                {
                    "neighbor_id": "10.0.0.2",
                    "priority": 1,
                    "state": "Full/DR",
                    "address": "10.0.0.2",
                    "interface": "eth0",
                },
            ],
            "raw_output": "OSPF neighbors",
        },
    ):
        resp = await client.get(
            "/api/v1/routing/ospf/neighbors",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True


@pytest.mark.asyncio
async def test_ospf_neighbors_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.ospf_neighbors",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/routing/ospf/neighbors",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_ospf_routes(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.ospf_routes",
        new_callable=AsyncMock,
        return_value={"count": 3, "raw_output": "routes"},
    ):
        resp = await client.get(
            "/api/v1/routing/ospf/routes",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["count"] == 3


@pytest.mark.asyncio
async def test_ospf_routes_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.ospf_routes",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/routing/ospf/routes",
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routing_requires_auth(client, bad_headers):
    resp = await client.get(
        "/api/v1/routing/bgp/status",
        headers=bad_headers,
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# RIP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rip_status(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.rip_status",
        new_callable=AsyncMock,
        return_value={
            "configured": True,
            "version": "2",
            "networks": ["10.0.0.0/24"],
            "neighbors": ["10.0.0.2"],
            "raw_output": "RIP status",
        },
    ):
        resp = await client.get(
            "/api/v1/routing/rip/status",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["version"] == "2"
    assert len(data["networks"]) == 1


@pytest.mark.asyncio
async def test_rip_status_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.rip_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/routing/rip/status",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_rip_routes(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.rip_routes",
        new_callable=AsyncMock,
        return_value={
            "count": 2,
            "routes": [
                {
                    "code": "R(n)",
                    "network": "10.0.0.0/24",
                    "nexthop": "10.0.0.2",
                    "metric": 2,
                },
                {"code": "C", "network": "192.168.1.0/24", "nexthop": "", "metric": 1},
            ],
            "raw_output": "RIP routes",
        },
    ):
        resp = await client.get(
            "/api/v1/routing/rip/routes",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["routes"]) == 2


@pytest.mark.asyncio
async def test_rip_routes_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.rip_routes",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/routing/rip/routes",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_rip_requires_auth(client, bad_headers):
    resp = await client.get(
        "/api/v1/routing/rip/status",
        headers=bad_headers,
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# BFD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bfd_peers(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.bfd_peers",
        new_callable=AsyncMock,
        return_value={
            "configured": True,
            "peers": [
                {
                    "peer": "10.0.0.2",
                    "interface": "eth0",
                    "status": "up",
                    "uptime": "01:00:00",
                }
            ],
            "count": 1,
            "raw_output": "bfd peers",
        },
    ):
        resp = await client.get("/api/v1/routing/bfd/peers", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_bfd_peers_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.bfd_peers",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/routing/bfd/peers", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_bfd_summary(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.bfd_summary",
        new_callable=AsyncMock,
        return_value={"configured": True, "raw_output": "counters"},
    ):
        resp = await client.get("/api/v1/routing/bfd/summary", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["configured"] is True


@pytest.mark.asyncio
async def test_bfd_summary_error(client, headers):
    with patch(
        "dawos_agent.routers.routing.routing.bfd_summary",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/routing/bfd/summary", headers=headers)
    assert resp.status_code == 500
