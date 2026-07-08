"""Tests for routers/pppoe.py — endpoint tests with mocked services."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.models.schemas import PppoeInterface

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_PPPOE_IFACES = [
    PppoeInterface(name="eth0.100", options=""),
    PppoeInterface(name="eth0.200", options="padi-limit=0"),
]


# ---------------------------------------------------------------------------
# List PPPoE interfaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pppoe_interfaces(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.list_pppoe_interfaces",
        return_value=MOCK_PPPOE_IFACES,
    ):
        resp = await client.get("/api/v1/pppoe/interfaces", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["interfaces"][0]["name"] == "eth0.100"
    assert data["interfaces"][1]["name"] == "eth0.200"
    assert data["interfaces"][1]["options"] == "padi-limit=0"


@pytest.mark.asyncio
async def test_list_pppoe_interfaces_empty(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.list_pppoe_interfaces", return_value=[]
    ):
        resp = await client.get("/api/v1/pppoe/interfaces", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_list_pppoe_interfaces_not_found(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.list_pppoe_interfaces",
        side_effect=FileNotFoundError("Config file not found"),
    ):
        resp = await client.get("/api/v1/pppoe/interfaces", headers=headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_pppoe_interfaces_error(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.list_pppoe_interfaces",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/pppoe/interfaces", headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Add PPPoE interface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_pppoe_interface(client, headers):
    with (
        patch(
            "dawos_agent.routers.pppoe.pppoe.add_pppoe_interface",
            return_value="Added eth0.300 to [pppoe] section",
        ),
        patch("dawos_agent.routers.pppoe.reload_config", new_callable=AsyncMock),
    ):
        resp = await client.post(
            "/api/v1/pppoe/interfaces",
            headers=headers,
            json={"interface": "eth0.300"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Added" in data["message"]


@pytest.mark.asyncio
async def test_add_pppoe_interface_with_options(client, headers):
    with (
        patch(
            "dawos_agent.routers.pppoe.pppoe.add_pppoe_interface",
            return_value="Added eth0.300 to [pppoe] section",
        ),
        patch("dawos_agent.routers.pppoe.reload_config", new_callable=AsyncMock),
    ):
        resp = await client.post(
            "/api/v1/pppoe/interfaces",
            headers=headers,
            json={"interface": "eth0.300", "options": "padi-limit=5"},
        )

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_add_pppoe_interface_reload_fails(client, headers):
    """Config is saved but reload fails — should still return success with warning."""
    with (
        patch(
            "dawos_agent.routers.pppoe.pppoe.add_pppoe_interface",
            return_value="Added eth0.300 to [pppoe] section",
        ),
        patch(
            "dawos_agent.routers.pppoe.reload_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("accel-cmd failed"),
        ),
    ):
        resp = await client.post(
            "/api/v1/pppoe/interfaces",
            headers=headers,
            json={"interface": "eth0.300"},
        )

    assert resp.status_code == 200
    assert "reload failed" in resp.json()["message"]


@pytest.mark.asyncio
async def test_add_pppoe_interface_duplicate(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.add_pppoe_interface",
        side_effect=ValueError("already exists"),
    ):
        resp = await client.post(
            "/api/v1/pppoe/interfaces",
            headers=headers,
            json={"interface": "eth0.100"},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_add_pppoe_interface_config_not_found(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.add_pppoe_interface",
        side_effect=FileNotFoundError("Config file not found"),
    ):
        resp = await client.post(
            "/api/v1/pppoe/interfaces",
            headers=headers,
            json={"interface": "eth0.300"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_pppoe_interface_error(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.add_pppoe_interface",
        side_effect=Exception("unexpected"),
    ):
        resp = await client.post(
            "/api/v1/pppoe/interfaces",
            headers=headers,
            json={"interface": "eth0.300"},
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Remove PPPoE interface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_pppoe_interface(client, headers):
    with (
        patch(
            "dawos_agent.routers.pppoe.pppoe.remove_pppoe_interface",
            return_value="Removed eth0.100 from [pppoe] section",
        ),
        patch("dawos_agent.routers.pppoe.reload_config", new_callable=AsyncMock),
    ):
        resp = await client.delete("/api/v1/pppoe/interfaces/eth0.100", headers=headers)

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_pppoe_interface_reload_fails(client, headers):
    with (
        patch(
            "dawos_agent.routers.pppoe.pppoe.remove_pppoe_interface",
            return_value="Removed eth0.100",
        ),
        patch(
            "dawos_agent.routers.pppoe.reload_config",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fail"),
        ),
    ):
        resp = await client.delete("/api/v1/pppoe/interfaces/eth0.100", headers=headers)

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_pppoe_interface_not_found(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.remove_pppoe_interface",
        side_effect=ValueError("not found"),
    ):
        resp = await client.delete("/api/v1/pppoe/interfaces/eth0.999", headers=headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_pppoe_interface_config_not_found(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.remove_pppoe_interface",
        side_effect=FileNotFoundError("Config not found"),
    ):
        resp = await client.delete("/api/v1/pppoe/interfaces/eth0.100", headers=headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_pppoe_interface_error(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.pppoe.remove_pppoe_interface",
        side_effect=Exception("unexpected"),
    ):
        resp = await client.delete("/api/v1/pppoe/interfaces/eth0.100", headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pppoe_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/pppoe/interfaces", headers=bad_headers)
    assert resp.status_code == 401
