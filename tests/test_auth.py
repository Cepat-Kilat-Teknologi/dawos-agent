"""Tests for authentication middleware."""

import pytest


@pytest.mark.asyncio
async def test_protected_endpoint_requires_key(client):
    """Requests without API key should get 401."""
    resp = await client.get("/api/v1/system/info")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_rejects_bad_key(client, bad_headers):
    """Requests with wrong API key should get 401."""
    resp = await client.get("/api/v1/system/info", headers=bad_headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_accepts_good_key(client, headers):
    """Requests with correct API key should succeed."""
    resp = await client.get("/api/v1/system/info", headers=headers)
    assert resp.status_code == 200
