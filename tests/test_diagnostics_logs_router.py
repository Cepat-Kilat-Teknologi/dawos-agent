"""Tests for routers/diagnostics.py + routers/logs.py — endpoint tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Diagnostics — doctor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_doctor(client, headers):
    with patch(
        "dawos_agent.routers.diagnostics.diagnostics.run_doctor",
        new_callable=AsyncMock,
        return_value={
            "checks": [
                {"name": "service", "status": "ok", "detail": "running"},
                {"name": "nat", "status": "warn", "detail": "no NAT"},
            ],
            "total": 2,
            "fails": 0,
            "warns": 1,
            "healthy": True,
        },
    ):
        resp = await client.get(
            "/api/v1/diagnostics/doctor",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["healthy"] is True


@pytest.mark.asyncio
async def test_doctor_error(client, headers):
    with patch(
        "dawos_agent.routers.diagnostics.diagnostics.run_doctor",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/diagnostics/doctor",
            headers=headers,
        )

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_doctor_requires_auth(client, bad_headers):
    resp = await client.get(
        "/api/v1/diagnostics/doctor",
        headers=bad_headers,
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logs — tail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tail_logs(client, headers):
    with patch(
        "dawos_agent.routers.logs.logs.get_logs",
        new_callable=AsyncMock,
        return_value={
            "lines": ["line1", "line2"],
            "count": 2,
            "source": "accel-ppp",
        },
    ):
        resp = await client.get(
            "/api/v1/logs/tail",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["source"] == "accel-ppp"


@pytest.mark.asyncio
async def test_tail_logs_custom_params(client, headers):
    with patch(
        "dawos_agent.routers.logs.logs.get_logs",
        new_callable=AsyncMock,
        return_value={
            "lines": ["log line"],
            "count": 1,
            "source": "frr",
        },
    ):
        resp = await client.get(
            "/api/v1/logs/tail?lines=50&unit=frr",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["source"] == "frr"


@pytest.mark.asyncio
async def test_tail_logs_error(client, headers):
    with patch(
        "dawos_agent.routers.logs.logs.get_logs",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get(
            "/api/v1/logs/tail",
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Logs — SSE stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_logs(client, headers):
    async def mock_gen(unit="accel-ppp"):
        yield 'data: {"line": "event1", "source": "accel-ppp"}\n\n'

    with patch(
        "dawos_agent.routers.logs.logs.log_stream_events",
        side_effect=mock_gen,
    ):
        resp = await client.get(
            "/api/v1/logs/stream",
            headers=headers,
        )

    assert resp.status_code == 200
    assert "event1" in resp.text


@pytest.mark.asyncio
async def test_logs_requires_auth(client, bad_headers):
    resp = await client.get(
        "/api/v1/logs/tail",
        headers=bad_headers,
    )
    assert resp.status_code == 401
