"""Regression tests for path/query injection guards (DA-L07 / DA-C01).

Shell metacharacters in path and query parameters that flow toward
``accel-cmd`` / shell sinks must be rejected with HTTP 422 by the
``RE_SAFE_*`` ``Path``/``Query`` patterns, before any command runs.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["a;id", "a b", "a$x", "a|b"])
async def test_session_find_rejects_metachars(client, headers, bad):
    """GET /sessions/find/{username} rejects shell metacharacters."""
    resp = await client.get(f"/api/v1/sessions/find/{bad}", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_session_by_sid_rejects_metachars(client, headers):
    """GET /sessions/control/by-sid/{sid} rejects shell metacharacters."""
    resp = await client.get("/api/v1/sessions/control/by-sid/a;id", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_logs_tail_unit_rejects_metachars(client, headers):
    """GET /logs/tail?unit= rejects shell metacharacters in the unit."""
    resp = await client.get(
        "/api/v1/logs/tail", headers=headers, params={"unit": "accel-ppp;id"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_traffic_queue_rejects_metachars(client, headers):
    """GET /traffic/queue/{username} rejects shell metacharacters."""
    resp = await client.get("/api/v1/traffic/queue/a;id", headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_vlan_delete_rejects_metachars(client, headers):
    """DELETE /network/vlans/{name} rejects shell metacharacters."""
    resp = await client.delete("/api/v1/network/vlans/eth0;reboot", headers=headers)
    assert resp.status_code == 422
