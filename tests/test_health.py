"""Tests for the health endpoint (public, no auth)."""

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
