"""Tests for the request-ID middleware."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_request_id_generated_when_absent(client):
    """Response should contain an X-Request-ID even if caller omits it."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    rid = resp.headers.get("x-request-id")
    assert rid, "X-Request-ID header must be present"
    assert len(rid) == 32  # uuid4().hex is 32 hex chars


@pytest.mark.asyncio
async def test_request_id_echoed_when_provided(client):
    """Caller-supplied X-Request-ID should be echoed back verbatim."""
    custom_id = "my-trace-id-abc123"
    resp = await client.get("/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id") == custom_id


@pytest.mark.asyncio
async def test_request_id_unique_across_requests(client):
    """Each request without a caller ID should get a distinct trace ID."""
    resp1 = await client.get("/health")
    resp2 = await client.get("/health")
    rid1 = resp1.headers.get("x-request-id")
    rid2 = resp2.headers.get("x-request-id")
    assert rid1 != rid2, "Auto-generated IDs must be unique per request"


@pytest.mark.asyncio
async def test_request_id_on_protected_endpoint(client, headers):
    """X-Request-ID should appear on authenticated endpoints too."""
    resp = await client.get("/api/v1/system/info", headers=headers)
    assert resp.headers.get("x-request-id")


@pytest.mark.asyncio
async def test_request_id_on_error_response(client):
    """X-Request-ID should appear even on 401 responses."""
    resp = await client.get("/api/v1/sessions")
    assert resp.status_code == 401
    assert resp.headers.get("x-request-id")
