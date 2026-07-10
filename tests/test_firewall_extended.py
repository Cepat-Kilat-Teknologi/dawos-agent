"""Tests for NAT egress, conntrack, SNMP endpoints in routers/firewall.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# NAT egress map
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_egress_map(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.get_egress_map",
        new_callable=AsyncMock,
        return_value=[
            {"customer_ip": "10.0.0.2", "public_ip": "1.2.3.4"},
        ],
    ):
        resp = await client.get(
            "/api/v1/firewall/nat/egress",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["entries"][0]["customer_ip"] == "10.0.0.2"


@pytest.mark.asyncio
async def test_get_egress_map_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.get_egress_map",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/firewall/nat/egress",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_set_egress(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.set_egress",
        new_callable=AsyncMock,
        return_value="Egress set",
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/egress",
            headers=headers,
            json={"target": "10.0.0.2", "public_ip": "1.2.3.4"},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_set_egress_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.set_egress",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/egress",
            headers=headers,
            json={"target": "10.0.0.2", "public_ip": "1.2.3.4"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_clear_egress(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.clear_egress",
        new_callable=AsyncMock,
        return_value="Egress cleared",
    ):
        resp = await client.delete(
            "/api/v1/firewall/nat/egress/10.0.0.2",
            headers=headers,
        )

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_clear_egress_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.clear_egress",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.delete(
            "/api/v1/firewall/nat/egress/10.0.0.2",
            headers=headers,
        )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


@pytest.mark.asyncio
async def test_clear_egress_not_found(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.clear_egress",
        new_callable=AsyncMock,
        side_effect=RuntimeError("No such file or directory"),
    ):
        resp = await client.delete(
            "/api/v1/firewall/nat/egress/10.0.0.2",
            headers=headers,
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Public IP management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_public_ip(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.add_public_ip",
        new_callable=AsyncMock,
        return_value="Added 1.2.3.4",
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/public-ip",
            headers=headers,
            json={"public_ip": "1.2.3.4", "interface": "eth0"},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_add_public_ip_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.add_public_ip",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/public-ip",
            headers=headers,
            json={"public_ip": "1.2.3.4"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_remove_public_ip(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.remove_public_ip",
        new_callable=AsyncMock,
        return_value="Removed 1.2.3.4",
    ):
        resp = await client.delete(
            "/api/v1/firewall/nat/public-ip/1.2.3.4",
            headers=headers,
        )

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_public_ip_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.remove_public_ip",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.delete(
            "/api/v1/firewall/nat/public-ip/1.2.3.4",
            headers=headers,
        )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# NAT status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_nat_status(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.nat_status",
        new_callable=AsyncMock,
        return_value={
            "egress_map": [],
            "postrouting_rules": "snat",
            "bound_ips": "eth0 UP",
        },
    ):
        resp = await client.get(
            "/api/v1/firewall/nat/status",
            headers=headers,
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_full_nat_status_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.nat_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/firewall/nat/status",
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Box egress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_box_egress_status(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.box_egress_status",
        new_callable=AsyncMock,
        return_value={"enabled": True},
    ):
        resp = await client.get(
            "/api/v1/firewall/nat/box-egress",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_box_egress_status_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.box_egress_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/firewall/nat/box-egress",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_box_egress_toggle_on(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.box_egress_set",
        new_callable=AsyncMock,
        return_value="Box egress enabled",
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/box-egress",
            headers=headers,
            json={"action": "on"},
        )

    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_box_egress_toggle_off(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.box_egress_set",
        new_callable=AsyncMock,
        return_value="Box egress disabled",
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/box-egress",
            headers=headers,
            json={"action": "off"},
        )

    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_box_egress_toggle_invalid(client, headers):
    resp = await client.post(
        "/api/v1/firewall/nat/box-egress",
        headers=headers,
        json={"action": "maybe"},
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_box_egress_toggle_service_valueerror(client, headers):
    """Service-level ValueError still returns 400."""
    with patch(
        "dawos_agent.routers.firewall.nat.box_egress_set",
        new_callable=AsyncMock,
        side_effect=ValueError("nft command failed"),
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/box-egress",
            headers=headers,
            json={"action": "on"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_box_egress_toggle_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.nat.box_egress_set",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/box-egress",
            headers=headers,
            json={"action": "on"},
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Conntrack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conntrack_status(client, headers):
    with patch(
        "dawos_agent.routers.firewall.diagnostics.get_conntrack",
        new_callable=AsyncMock,
        return_value={
            "current_max": 524288,
            "recommended_min": 262144,
            "status": "ok",
            "detail": "nf_conntrack_max=524288",
        },
    ):
        resp = await client.get(
            "/api/v1/firewall/conntrack",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["current_max"] == 524288


@pytest.mark.asyncio
async def test_conntrack_status_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.diagnostics.get_conntrack",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/firewall/conntrack",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_conntrack_tune(client, headers):
    with patch(
        "dawos_agent.routers.firewall.diagnostics.set_conntrack",
        new_callable=AsyncMock,
        return_value={
            "current_max": 524288,
            "recommended_min": 262144,
            "status": "ok",
            "detail": "nf_conntrack_max=524288",
        },
    ):
        resp = await client.put(
            "/api/v1/firewall/conntrack",
            headers=headers,
            json={"max_value": 524288},
        )

    assert resp.status_code == 200
    assert resp.json()["current_max"] == 524288


@pytest.mark.asyncio
async def test_conntrack_tune_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.diagnostics.set_conntrack",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.put(
            "/api/v1/firewall/conntrack",
            headers=headers,
            json={"max_value": 524288},
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# SNMP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snmp_status(client, headers):
    with patch(
        "dawos_agent.routers.firewall.diagnostics.snmp_status",
        new_callable=AsyncMock,
        return_value={
            "name": "snmp",
            "status": "ok",
            "detail": "snmpd running, port 161 open",
        },
    ):
        resp = await client.get(
            "/api/v1/firewall/snmp",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is True
    assert data["port_open"] is True


@pytest.mark.asyncio
async def test_snmp_status_not_running(client, headers):
    with patch(
        "dawos_agent.routers.firewall.diagnostics.snmp_status",
        new_callable=AsyncMock,
        return_value={
            "name": "snmp",
            "status": "warn",
            "detail": "snmpd not running",
        },
    ):
        resp = await client.get(
            "/api/v1/firewall/snmp",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is False
    assert data["port_open"] is False


@pytest.mark.asyncio
async def test_snmp_status_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.diagnostics.snmp_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/firewall/snmp",
            headers=headers,
        )

    assert resp.status_code == 500
