"""Tests for the authentication management router (DAWOS-16).

Covers:
* ``POST /api/v1/auth/generate-key`` — admin-only key generation.
* ``GET /api/v1/auth/rbac-status`` — admin-only RBAC status.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# POST /api/v1/auth/generate-key
# ---------------------------------------------------------------------------


class TestGenerateKey:
    """POST /api/v1/auth/generate-key endpoint tests."""

    @pytest.mark.asyncio
    async def test_rejects_without_key(self, client) -> None:
        """Request without X-API-Key returns 401."""
        resp = await client.post("/api/v1/auth/generate-key")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_bad_key(self, client, bad_headers) -> None:
        """Invalid API key returns 401."""
        resp = await client.post("/api/v1/auth/generate-key", headers=bad_headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_viewer_key(self, client, viewer_headers) -> None:
        """Viewer-level key cannot access the admin endpoint."""
        resp = await client.post("/api/v1/auth/generate-key", headers=viewer_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rejects_operator_key(self, client, operator_headers) -> None:
        """Operator-level key cannot access the admin endpoint."""
        resp = await client.post("/api/v1/auth/generate-key", headers=operator_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_generates_key_for_admin(self, client, admin_headers) -> None:
        """Admin-level key gets a freshly generated API key."""
        resp = await client.post("/api/v1/auth/generate-key", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "key" in body
        assert len(body["key"]) > 20  # 32-byte URL-safe base64 ≈ 43 chars
        assert "hint" in body

    @pytest.mark.asyncio
    async def test_generates_key_for_primary(self, client, headers) -> None:
        """Primary API key (always admin) can generate keys."""
        resp = await client.post("/api/v1/auth/generate-key", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "key" in body

    @pytest.mark.asyncio
    async def test_generated_keys_are_unique(self, client, admin_headers) -> None:
        """Two successive calls produce different keys."""
        key1 = (
            await client.post("/api/v1/auth/generate-key", headers=admin_headers)
        ).json()["key"]
        key2 = (
            await client.post("/api/v1/auth/generate-key", headers=admin_headers)
        ).json()["key"]
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_key_length(self, client, admin_headers) -> None:
        """Generated key has correct length for 32-byte URL-safe base64."""
        resp = await client.post("/api/v1/auth/generate-key", headers=admin_headers)
        key = resp.json()["key"]
        # secrets.token_urlsafe(32) produces 43-char string
        assert len(key) == 43


# ---------------------------------------------------------------------------
# GET /api/v1/auth/rbac-status
# ---------------------------------------------------------------------------


class TestRbacStatus:
    """GET /api/v1/auth/rbac-status endpoint tests."""

    @pytest.mark.asyncio
    async def test_rejects_without_key(self, client) -> None:
        """Request without X-API-Key returns 401."""
        resp = await client.get("/api/v1/auth/rbac-status")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_bad_key(self, client, bad_headers) -> None:
        """Invalid API key returns 401."""
        resp = await client.get("/api/v1/auth/rbac-status", headers=bad_headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_viewer(self, client, viewer_headers) -> None:
        """Viewer key cannot access RBAC status."""
        resp = await client.get("/api/v1/auth/rbac-status", headers=viewer_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rejects_operator(self, client, operator_headers) -> None:
        """Operator key cannot access RBAC status."""
        resp = await client.get("/api/v1/auth/rbac-status", headers=operator_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_status_for_admin(self, client, admin_headers) -> None:
        """Admin key can read RBAC status."""
        resp = await client.get("/api/v1/auth/rbac-status", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "rbac_enabled" in body
        assert "extra_keys_count" in body
        # conftest sets up 3 extra keys (viewer, operator, admin)
        assert body["rbac_enabled"] is True
        assert body["extra_keys_count"] == 3

    @pytest.mark.asyncio
    async def test_returns_status_for_primary(self, client, headers) -> None:
        """Primary key (always admin) can read RBAC status."""
        resp = await client.get("/api/v1/auth/rbac-status", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["rbac_enabled"] is True
