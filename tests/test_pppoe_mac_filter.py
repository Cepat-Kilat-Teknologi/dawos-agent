"""Tests for MAC filter endpoints in routers/pppoe.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# MAC filter — list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_mac_filter(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.mac_filter",
        new_callable=AsyncMock,
        return_value="AA:BB:CC:DD:EE:FF\n11:22:33:44:55:66",
    ):
        resp = await client.get(
            "/api/v1/pppoe/mac-filter",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2  # two lines with ":"


@pytest.mark.asyncio
async def test_list_mac_filter_empty(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.mac_filter",
        new_callable=AsyncMock,
        return_value="",
    ):
        resp = await client.get(
            "/api/v1/pppoe/mac-filter",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_list_mac_filter_error(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.mac_filter",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/pppoe/mac-filter",
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# MAC filter — add
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_mac(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.mac_filter",
        new_callable=AsyncMock,
        return_value="ok",
    ):
        resp = await client.post(
            "/api/v1/pppoe/mac-filter",
            headers=headers,
            json={"mac": "AA:BB:CC:DD:EE:FF"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "AA:BB:CC:DD:EE:FF" in data["message"]


@pytest.mark.asyncio
async def test_add_mac_error(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.mac_filter",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/pppoe/mac-filter",
            headers=headers,
            json={"mac": "AA:BB:CC:DD:EE:FF"},
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# MAC filter — delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_mac(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.mac_filter",
        new_callable=AsyncMock,
        return_value="ok",
    ):
        resp = await client.delete(
            "/api/v1/pppoe/mac-filter/AA:BB:CC:DD:EE:FF",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "AA:BB:CC:DD:EE:FF" in data["message"]


@pytest.mark.asyncio
async def test_delete_mac_error(client, headers):
    with patch(
        "dawos_agent.routers.pppoe.mac_filter",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.delete(
            "/api/v1/pppoe/mac-filter/AA:BB:CC:DD:EE:FF",
            headers=headers,
        )

    assert resp.status_code == 500
