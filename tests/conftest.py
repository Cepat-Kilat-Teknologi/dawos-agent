"""Shared test fixtures."""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# RBAC test keys — must be set before importing app
# ---------------------------------------------------------------------------

#: Primary API key (always admin).
_TEST_PRIMARY_KEY = "test-key-12345"

#: Additional keys for RBAC testing.
_TEST_VIEWER_KEY = "test-viewer-key"
_TEST_OPERATOR_KEY = "test-operator-key"
_TEST_ADMIN_KEY = "test-admin-key"

# Create a temporary keys file for RBAC tests.
_keys_data = {
    _TEST_VIEWER_KEY: "viewer",
    _TEST_OPERATOR_KEY: "operator",
    _TEST_ADMIN_KEY: "admin",
}
_keys_fd, _keys_path = tempfile.mkstemp(suffix=".json", prefix="dawos-test-keys-")
with os.fdopen(_keys_fd, "w") as f:
    json.dump(_keys_data, f)

os.environ["DAWOS_API_KEY"] = _TEST_PRIMARY_KEY
os.environ["DAWOS_API_KEYS_FILE"] = _keys_path
os.environ["DAWOS_ACCEL_CMD"] = "/usr/bin/accel-cmd"

from dawos_agent.app import app  # noqa: E402


@pytest.fixture
def headers():
    """Auth headers for protected endpoints (admin via primary key)."""
    return {"X-API-Key": _TEST_PRIMARY_KEY}


@pytest.fixture
def bad_headers():
    """Invalid auth headers."""
    return {"X-API-Key": "wrong-key"}


@pytest.fixture
def viewer_headers():
    """Auth headers with viewer (read-only) role."""
    return {"X-API-Key": _TEST_VIEWER_KEY}


@pytest.fixture
def operator_headers():
    """Auth headers with operator (read+write) role."""
    return {"X-API-Key": _TEST_OPERATOR_KEY}


@pytest.fixture
def admin_headers():
    """Auth headers with admin (full access) role."""
    return {"X-API-Key": _TEST_ADMIN_KEY}


@pytest.fixture
async def client():
    """Async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
