"""Tests for routers/csv_export_router.py — CSV export endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GET /export/sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_sessions(client, headers):
    """Sessions CSV export returns text/csv response."""
    csv_data = '"ifname","username"\n"ppp0","user1"\n'
    with patch(
        "dawos_agent.routers.csv_export_router.csv_export.export_sessions_csv",
        new_callable=AsyncMock,
        return_value=csv_data,
    ):
        resp = await client.get("/api/v1/export/sessions", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "sessions.csv" in resp.headers["content-disposition"]
    assert resp.text == csv_data


@pytest.mark.asyncio
async def test_export_sessions_error(client, headers):
    """Internal error returns 500."""
    with patch(
        "dawos_agent.routers.csv_export_router.csv_export.export_sessions_csv",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/export/sessions", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /export/history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_history(client, headers):
    """History CSV export returns text/csv response."""
    csv_data = '"id","snapshot_at","username"\n"1","2026-01-01","alice"\n'
    with patch(
        "dawos_agent.routers.csv_export_router.csv_export.export_history_csv",
        new_callable=AsyncMock,
        return_value=csv_data,
    ):
        resp = await client.get("/api/v1/export/history", headers=headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "history.csv" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_export_history_with_filters(client, headers):
    """History CSV export passes query params to service."""
    csv_data = '"id","snapshot_at"\n'
    with patch(
        "dawos_agent.routers.csv_export_router.csv_export.export_history_csv",
        new_callable=AsyncMock,
        return_value=csv_data,
    ) as mock_export:
        resp = await client.get(
            "/api/v1/export/history?username=alice&ip=10.0.0.1"
            "&start=2026-01-01&end=2026-12-31&limit=500",
            headers=headers,
        )
    assert resp.status_code == 200
    mock_export.assert_called_once_with(
        username="alice",
        ip="10.0.0.1",
        start="2026-01-01",
        end="2026-12-31",
        limit=500,
    )


@pytest.mark.asyncio
async def test_export_history_error(client, headers):
    """Internal error returns 500."""
    with patch(
        "dawos_agent.routers.csv_export_router.csv_export.export_history_csv",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/export/history", headers=headers)
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_sessions_requires_auth(client, bad_headers):
    """Sessions export requires authentication."""
    resp = await client.get("/api/v1/export/sessions", headers=bad_headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_export_history_requires_auth(client, bad_headers):
    """History export requires authentication."""
    resp = await client.get("/api/v1/export/history", headers=bad_headers)
    assert resp.status_code == 401
