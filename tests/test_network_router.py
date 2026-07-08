"""Tests for routers/network.py — endpoint tests with mocked services."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.models.schemas import (
    DnsConfig,
    InterfaceAddress,
    InterfaceDetail,
    RouteEntry,
    VlanInfo,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_IFACES = [
    InterfaceDetail(
        name="eth0",
        index=2,
        mac_address="52:54:00:12:34:56",
        mtu=1500,
        state="UP",
        flags=["BROADCAST", "UP"],
        addresses=[InterfaceAddress(family="inet", address="10.0.0.1", prefix_len=24)],
        link_type="ether",
    ),
    InterfaceDetail(
        name="ppp0",
        index=3,
        mac_address="",
        mtu=1492,
        state="UP",
        flags=["POINTOPOINT", "UP"],
        addresses=[
            InterfaceAddress(family="inet", address="100.64.0.1", prefix_len=32)
        ],
        link_type="ppp",
    ),
]

MOCK_ROUTES = [
    RouteEntry(
        destination="default", gateway="10.0.0.254", device="eth0", protocol="dhcp"
    ),
    RouteEntry(destination="10.0.0.0/24", device="eth0", protocol="kernel"),
]

MOCK_VLANS = [
    VlanInfo(
        name="eth0.100",
        parent="eth0",
        vlan_id=100,
        protocol="802.1Q",
        state="UP",
        mac_address="52:54:00:12:34:56",
        mtu=1500,
        addresses=[
            InterfaceAddress(family="inet", address="192.168.100.1", prefix_len=24)
        ],
    ),
    VlanInfo(
        name="eth0.200",
        parent="eth0",
        vlan_id=200,
        protocol="802.1Q",
        state="DOWN",
        mac_address="52:54:00:12:34:56",
        mtu=1500,
    ),
]


# ---------------------------------------------------------------------------
# Interface endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_interfaces(client, headers):
    with patch(
        "dawos_agent.routers.network.network.list_interfaces",
        new_callable=AsyncMock,
        return_value=MOCK_IFACES,
    ):
        resp = await client.get("/api/v1/network/interfaces", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["interfaces"][0]["name"] == "eth0"


@pytest.mark.asyncio
async def test_list_interfaces_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.list_interfaces",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/network/interfaces", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_get_interface(client, headers):
    with patch(
        "dawos_agent.routers.network.network.get_interface",
        new_callable=AsyncMock,
        return_value=MOCK_IFACES[0],
    ):
        resp = await client.get("/api/v1/network/interfaces/eth0", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["name"] == "eth0"


@pytest.mark.asyncio
async def test_get_interface_not_found(client, headers):
    with patch(
        "dawos_agent.routers.network.network.get_interface",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Interface not found"),
    ):
        resp = await client.get("/api/v1/network/interfaces/eth99", headers=headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_configure_interface(client, headers):
    with patch(
        "dawos_agent.routers.network.network.configure_interface",
        new_callable=AsyncMock,
        return_value="Interface eth0: added 10.0.0.5/24",
    ):
        resp = await client.put(
            "/api/v1/network/interfaces/eth0",
            headers=headers,
            json={"address": "10.0.0.5/24"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["interface"] == "eth0"


@pytest.mark.asyncio
async def test_configure_interface_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.configure_interface",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.put(
            "/api/v1/network/interfaces/eth0",
            headers=headers,
            json={"address": "10.0.0.5/24"},
        )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# VLAN endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_vlan(client, headers):
    with patch(
        "dawos_agent.routers.network.network.create_vlan",
        new_callable=AsyncMock,
        return_value="eth0.100",
    ):
        resp = await client.post(
            "/api/v1/network/vlans",
            headers=headers,
            json={"parent": "eth0", "vlan_id": 100},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["name"] == "eth0.100"


@pytest.mark.asyncio
async def test_create_vlan_with_address(client, headers):
    with patch(
        "dawos_agent.routers.network.network.create_vlan",
        new_callable=AsyncMock,
        return_value="eth0.200",
    ):
        resp = await client.post(
            "/api/v1/network/vlans",
            headers=headers,
            json={"parent": "eth0", "vlan_id": 200, "address": "192.168.200.1/24"},
        )

    assert resp.status_code == 200
    assert resp.json()["name"] == "eth0.200"


@pytest.mark.asyncio
async def test_create_vlan_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.create_vlan",
        new_callable=AsyncMock,
        side_effect=RuntimeError("exists"),
    ):
        resp = await client.post(
            "/api/v1/network/vlans",
            headers=headers,
            json={"parent": "eth0", "vlan_id": 100},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_vlan(client, headers):
    with patch(
        "dawos_agent.routers.network.network.delete_vlan",
        new_callable=AsyncMock,
        return_value="Deleted eth0.100",
    ):
        resp = await client.delete("/api/v1/network/vlans/eth0.100", headers=headers)

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_vlan_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.delete_vlan",
        new_callable=AsyncMock,
        side_effect=RuntimeError("not found"),
    ):
        resp = await client.delete("/api/v1/network/vlans/eth0.999", headers=headers)

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# VLAN auto-detect endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_vlans(client, headers):
    with patch(
        "dawos_agent.routers.network.network.list_vlans",
        new_callable=AsyncMock,
        return_value=MOCK_VLANS,
    ):
        resp = await client.get("/api/v1/network/vlans", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["vlans"][0]["name"] == "eth0.100"
    assert data["vlans"][0]["parent"] == "eth0"
    assert data["vlans"][0]["vlan_id"] == 100
    assert data["vlans"][0]["protocol"] == "802.1Q"
    assert data["vlans"][0]["state"] == "UP"
    assert data["vlans"][1]["state"] == "DOWN"


@pytest.mark.asyncio
async def test_list_vlans_empty(client, headers):
    with patch(
        "dawos_agent.routers.network.network.list_vlans",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get("/api/v1/network/vlans", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_list_vlans_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.list_vlans",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/network/vlans", headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# VLAN state (enable/disable) endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_vlan_state_up(client, headers):
    with patch(
        "dawos_agent.routers.network.network.set_vlan_state",
        new_callable=AsyncMock,
        return_value="VLAN eth0.100 set to up",
    ):
        resp = await client.put(
            "/api/v1/network/vlans/eth0.100",
            headers=headers,
            json={"state": "up"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["name"] == "eth0.100"
    assert data["state"] == "up"


@pytest.mark.asyncio
async def test_set_vlan_state_down(client, headers):
    with patch(
        "dawos_agent.routers.network.network.set_vlan_state",
        new_callable=AsyncMock,
        return_value="VLAN eth0.100 set to down",
    ):
        resp = await client.put(
            "/api/v1/network/vlans/eth0.100",
            headers=headers,
            json={"state": "down"},
        )

    assert resp.status_code == 200
    assert resp.json()["state"] == "down"


@pytest.mark.asyncio
async def test_set_vlan_state_invalid(client, headers):
    with patch(
        "dawos_agent.routers.network.network.set_vlan_state",
        new_callable=AsyncMock,
        side_effect=ValueError("Invalid state"),
    ):
        resp = await client.put(
            "/api/v1/network/vlans/eth0.100",
            headers=headers,
            json={"state": "invalid"},
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_set_vlan_state_not_found(client, headers):
    with patch(
        "dawos_agent.routers.network.network.set_vlan_state",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no such device"),
    ):
        resp = await client.put(
            "/api/v1/network/vlans/eth0.999",
            headers=headers,
            json={"state": "up"},
        )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Route endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_routes(client, headers):
    with patch(
        "dawos_agent.routers.network.network.list_routes",
        new_callable=AsyncMock,
        return_value=MOCK_ROUTES,
    ):
        resp = await client.get("/api/v1/network/routes", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["routes"][0]["destination"] == "default"


@pytest.mark.asyncio
async def test_list_routes_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.list_routes",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/network/routes", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_add_route(client, headers):
    with patch(
        "dawos_agent.routers.network.network.add_route",
        new_callable=AsyncMock,
        return_value="Route added",
    ):
        resp = await client.post(
            "/api/v1/network/routes",
            headers=headers,
            json={"destination": "172.16.0.0/16", "gateway": "10.0.0.254"},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_add_route_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.add_route",
        new_callable=AsyncMock,
        side_effect=RuntimeError("exists"),
    ):
        resp = await client.post(
            "/api/v1/network/routes",
            headers=headers,
            json={"destination": "172.16.0.0/16", "gateway": "10.0.0.254"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_route(client, headers):
    with patch(
        "dawos_agent.routers.network.network.delete_route",
        new_callable=AsyncMock,
        return_value="Route deleted",
    ):
        resp = await client.request(
            "DELETE",
            "/api/v1/network/routes",
            headers=headers,
            json={"destination": "172.16.0.0/16"},
        )

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_route_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.delete_route",
        new_callable=AsyncMock,
        side_effect=RuntimeError("not found"),
    ):
        resp = await client.request(
            "DELETE",
            "/api/v1/network/routes",
            headers=headers,
            json={"destination": "172.16.0.0/16"},
        )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# DNS endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_dns(client, headers):
    mock_config = DnsConfig(
        nameservers=["8.8.8.8", "1.1.1.1"], search_domains=["example.com"]
    )
    with patch("dawos_agent.routers.network.network.get_dns", return_value=mock_config):
        resp = await client.get("/api/v1/network/dns", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["config"]["nameservers"] == ["8.8.8.8", "1.1.1.1"]


@pytest.mark.asyncio
async def test_get_dns_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.get_dns", side_effect=Exception("fail")
    ):
        resp = await client.get("/api/v1/network/dns", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_set_dns(client, headers):
    with patch("dawos_agent.routers.network.network.set_dns") as mock_set:
        resp = await client.put(
            "/api/v1/network/dns",
            headers=headers,
            json={"nameservers": ["8.8.8.8"], "search_domains": ["example.com"]},
        )

    assert resp.status_code == 200
    assert resp.json()["message"] == "DNS updated"
    mock_set.assert_called_once()


@pytest.mark.asyncio
async def test_set_dns_error(client, headers):
    with patch(
        "dawos_agent.routers.network.network.set_dns",
        side_effect=Exception("permission denied"),
    ):
        resp = await client.put(
            "/api/v1/network/dns",
            headers=headers,
            json={"nameservers": ["8.8.8.8"]},
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/network/interfaces", headers=bad_headers)
    assert resp.status_code == 401
