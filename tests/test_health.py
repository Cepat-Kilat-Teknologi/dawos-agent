"""Tests for the health endpoints (public, no auth)."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "node_name" in data
    assert "version" in data
    assert "uptime_seconds" in data


@pytest.mark.asyncio
async def test_health_no_auth_required(client):
    """Health endpoint should work without API key."""
    resp = await client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Readiness probe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_ok_when_accel_reachable(client):
    """GET /health/ready returns 200 when accel-ppp responds."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"1.0.0", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        resp = await client.get("/health/ready")

    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert data["checks"][0]["service"] == "accel-ppp"
    assert data["checks"][0]["reachable"] is True


@pytest.mark.asyncio
async def test_readiness_503_when_accel_unreachable(client):
    """GET /health/ready returns 503 when accel-ppp is down."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"", b"refused")
    mock_proc.returncode = 1

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        resp = await client.get("/health/ready")

    assert resp.status_code == 503
    data = resp.json()
    assert data["ready"] is False
    assert data["checks"][0]["reachable"] is False


@pytest.mark.asyncio
async def test_readiness_503_when_binary_missing(client):
    """GET /health/ready returns 503 when accel-cmd is not found."""
    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError("accel-cmd"),
    ):
        resp = await client.get("/health/ready")

    assert resp.status_code == 503
    data = resp.json()
    assert data["ready"] is False
    assert "accel-cmd" in data["checks"][0]["detail"]


@pytest.mark.asyncio
async def test_readiness_503_on_timeout(client):
    """GET /health/ready returns 503 when accel-cmd times out."""
    import asyncio as _aio

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=_aio.TimeoutError(),
    ):
        resp = await client.get("/health/ready")

    assert resp.status_code == 503
    assert resp.json()["ready"] is False


@pytest.mark.asyncio
async def test_readiness_no_auth_required(client):
    """Readiness probe should work without API key."""
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (b"1.0.0", b"")
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        resp = await client.get("/health/ready")

    assert resp.status_code == 200
