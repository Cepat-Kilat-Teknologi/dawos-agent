"""Tests for routers/pado_router.py — PADO delay endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /pppoe/pado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pado_delay(client, headers):
    with patch(
        "dawos_agent.routers.pado_router.pado_delay.get_pado_delay",
        return_value={"delay": 500, "min_sessions": 100, "description": "500ms"},
    ):
        resp = await client.get("/api/v1/pppoe/pado", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["delay"] == 500


@pytest.mark.asyncio
async def test_get_pado_delay_not_found(client, headers):
    with patch(
        "dawos_agent.routers.pado_router.pado_delay.get_pado_delay",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.get("/api/v1/pppoe/pado", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_pado_delay_error(client, headers):
    with patch(
        "dawos_agent.routers.pado_router.pado_delay.get_pado_delay",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/pppoe/pado", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# PUT /pppoe/pado
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_pado_delay(client, headers):
    with (
        patch(
            "dawos_agent.routers.pado_router.pado_delay.set_pado_delay",
            return_value="ok",
        ),
        patch(
            "dawos_agent.routers.pado_router.reload_config",
            new_callable=AsyncMock,
        ),
        patch(
            "dawos_agent.routers.pado_router.pado_delay.get_pado_delay",
            return_value={"delay": 1000, "min_sessions": 50, "description": "1000ms"},
        ),
    ):
        resp = await client.put(
            "/api/v1/pppoe/pado",
            json={"delay": 1000, "min_sessions": 50},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["delay"] == 1000


@pytest.mark.asyncio
async def test_set_pado_delay_reload_failure(client, headers):
    with (
        patch(
            "dawos_agent.routers.pado_router.pado_delay.set_pado_delay",
            return_value="ok",
        ),
        patch(
            "dawos_agent.routers.pado_router.reload_config",
            new_callable=AsyncMock,
            side_effect=Exception("reload fail"),
        ),
        patch(
            "dawos_agent.routers.pado_router.pado_delay.get_pado_delay",
            return_value={"delay": 500, "min_sessions": 0, "description": "500ms"},
        ),
    ):
        resp = await client.put(
            "/api/v1/pppoe/pado",
            json={"delay": 500},
            headers=headers,
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_set_pado_delay_bad_value(client, headers):
    with patch(
        "dawos_agent.routers.pado_router.pado_delay.set_pado_delay",
        side_effect=ValueError("invalid value"),
    ):
        resp = await client.put(
            "/api/v1/pppoe/pado",
            json={"delay": 0},
            headers=headers,
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_pado_delay_not_found(client, headers):
    with patch(
        "dawos_agent.routers.pado_router.pado_delay.set_pado_delay",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.put(
            "/api/v1/pppoe/pado",
            json={"delay": 100},
            headers=headers,
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_pado_delay_error(client, headers):
    with patch(
        "dawos_agent.routers.pado_router.pado_delay.set_pado_delay",
        side_effect=Exception("fail"),
    ):
        resp = await client.put(
            "/api/v1/pppoe/pado",
            json={"delay": 100},
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pado_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/pppoe/pado", headers=bad_headers)
    assert resp.status_code == 401
