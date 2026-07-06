"""Tests for routers/session_control.py — session control endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# by-sid
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_by_sid(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.session_by_sid",
        new_callable=AsyncMock,
        return_value={"sid": "abc", "ifname": "ppp0"},
    ):
        resp = await client.get("/api/v1/sessions/control/by-sid/abc", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["found"] is True


@pytest.mark.asyncio
async def test_session_by_sid_not_found(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.session_by_sid",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.get("/api/v1/sessions/control/by-sid/nope", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["found"] is False


@pytest.mark.asyncio
async def test_session_by_sid_error(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.session_by_sid",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/sessions/control/by-sid/x", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# by-ip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_by_ip(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.session_by_ip",
        new_callable=AsyncMock,
        return_value={"ip": "10.0.0.5"},
    ):
        resp = await client.get(
            "/api/v1/sessions/control/by-ip/10.0.0.5", headers=headers
        )
    assert resp.status_code == 200
    assert resp.json()["found"] is True


@pytest.mark.asyncio
async def test_session_by_ip_error(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.session_by_ip",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/sessions/control/by-ip/x", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_snapshot(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.session_snapshot",
        new_callable=AsyncMock,
        return_value={"username": "u1", "found": True, "sessions": [{}], "count": 1},
    ):
        resp = await client.get("/api/v1/sessions/control/snapshot/u1", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["found"] is True


@pytest.mark.asyncio
async def test_session_snapshot_error(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.session_snapshot",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/sessions/control/snapshot/u1", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_session(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.restart_session",
        new_callable=AsyncMock,
        return_value={
            "success": True,
            "username": "u1",
            "previous_interface": "ppp0",
            "message": "ok",
        },
    ):
        resp = await client.post(
            "/api/v1/sessions/control/restart",
            json={"username": "u1"},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_restart_session_error(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.restart_session",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/sessions/control/restart",
            json={"username": "u1"},
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# drop-by-mac
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drop_by_mac(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.drop_by_mac",
        new_callable=AsyncMock,
        return_value={"success": True, "dropped": 1, "message": "ok"},
    ):
        resp = await client.post(
            "/api/v1/sessions/control/drop-by-mac",
            json={"mac": "AA:BB:CC:DD:EE:FF"},
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["dropped"] == 1


@pytest.mark.asyncio
async def test_drop_by_mac_error(client, headers):
    with patch(
        "dawos_agent.routers.session_control.session_control.drop_by_mac",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/sessions/control/drop-by-mac",
            json={"mac": "AA:BB:CC:DD:EE:FF"},
            headers=headers,
        )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_control_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/sessions/control/by-sid/x", headers=bad_headers)
    assert resp.status_code == 401
