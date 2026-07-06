"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Set test API key before importing app
os.environ["DAWOS_API_KEY"] = "test-key-12345"
os.environ["DAWOS_ACCEL_CMD"] = "/usr/bin/accel-cmd"

from dawos_agent.app import app  # noqa: E402


@pytest.fixture
def headers():
    """Auth headers for protected endpoints."""
    return {"X-API-Key": "test-key-12345"}


@pytest.fixture
def bad_headers():
    """Invalid auth headers."""
    return {"X-API-Key": "wrong-key"}


@pytest.fixture
async def client():
    """Async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
