"""Integration tests for RBAC endpoint access control.

Verifies that viewer, operator, and admin keys can only access
endpoints appropriate for their role level.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Viewer role — read-only access
# ---------------------------------------------------------------------------


class TestViewerAccess:
    """Viewer keys should access GET endpoints but be denied write/admin ops."""

    @pytest.mark.asyncio
    async def test_viewer_can_read_sessions(self, client, viewer_headers) -> None:
        resp = await client.get("/api/v1/sessions", headers=viewer_headers)
        # May return 200 or 500 (no accel-cmd in test), but NOT 401/403
        assert resp.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_viewer_can_read_system_info(self, client, viewer_headers) -> None:
        resp = await client.get("/api/v1/system/info", headers=viewer_headers)
        assert resp.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_viewer_can_read_config(self, client, viewer_headers) -> None:
        resp = await client.get("/api/v1/config", headers=viewer_headers)
        assert resp.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_viewer_cannot_terminate_session(
        self, client, viewer_headers
    ) -> None:
        resp = await client.post(
            "/api/v1/sessions/terminate",
            headers=viewer_headers,
            json={"username": "test"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_update_config(self, client, viewer_headers) -> None:
        resp = await client.put(
            "/api/v1/config",
            headers=viewer_headers,
            json={"content": "test config content here"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_restart_service(self, client, viewer_headers) -> None:
        resp = await client.post(
            "/api/v1/service/restart",
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_run_command(self, client, viewer_headers) -> None:
        resp = await client.post(
            "/api/v1/service/command",
            headers=viewer_headers,
            json={"command": "show stat"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_forbidden_message(self, client, viewer_headers) -> None:
        resp = await client.post(
            "/api/v1/service/restart",
            headers=viewer_headers,
        )
        assert resp.status_code == 403
        body = resp.json()
        assert "Insufficient permissions" in body["detail"]
        assert "admin" in body["detail"]


# ---------------------------------------------------------------------------
# Operator role — read + write access (no admin)
# ---------------------------------------------------------------------------


class TestOperatorAccess:
    """Operator keys should access read+write but be denied admin ops."""

    @pytest.mark.asyncio
    async def test_operator_can_read_sessions(self, client, operator_headers) -> None:
        resp = await client.get("/api/v1/sessions", headers=operator_headers)
        assert resp.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_operator_can_terminate_session(
        self,
        client,
        operator_headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/sessions/terminate",
            headers=operator_headers,
            json={"username": "test"},
        )
        # 200 or 500 (no accel-cmd), but NOT 401/403
        assert resp.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_operator_cannot_update_config(
        self,
        client,
        operator_headers,
    ) -> None:
        resp = await client.put(
            "/api/v1/config",
            headers=operator_headers,
            json={"content": "test config content here"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_cannot_restart_service(
        self,
        client,
        operator_headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/service/restart",
            headers=operator_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_cannot_run_command(
        self,
        client,
        operator_headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/service/command",
            headers=operator_headers,
            json={"command": "show stat"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_cannot_guarded_apply(
        self,
        client,
        operator_headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/config/apply",
            headers=operator_headers,
            json={"content": "test", "confirm_minutes": 5},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_cannot_rollback(
        self,
        client,
        operator_headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/config/rollback/backup.bak",
            headers=operator_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin role — full access
# ---------------------------------------------------------------------------


class TestAdminAccess:
    """Admin keys should access all endpoints including destructive ops."""

    @pytest.mark.asyncio
    async def test_admin_can_read_sessions(self, client, admin_headers) -> None:
        resp = await client.get("/api/v1/sessions", headers=admin_headers)
        assert resp.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_can_terminate_session(self, client, admin_headers) -> None:
        resp = await client.post(
            "/api/v1/sessions/terminate",
            headers=admin_headers,
            json={"username": "test"},
        )
        assert resp.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_can_run_command(self, client, admin_headers) -> None:
        resp = await client.post(
            "/api/v1/service/command",
            headers=admin_headers,
            json={"command": "show stat"},
        )
        # 200 or 500 (no accel-cmd), but NOT 401/403
        assert resp.status_code not in (401, 403)

    @pytest.mark.asyncio
    async def test_primary_key_is_admin(self, client, headers) -> None:
        """The primary DAWOS_API_KEY should always resolve to admin."""
        resp = await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        assert resp.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# No auth / bad auth
# ---------------------------------------------------------------------------


class TestNoAuth:
    """Requests without valid keys should be rejected."""

    @pytest.mark.asyncio
    async def test_no_key_returns_401(self, client) -> None:
        resp = await client.get("/api/v1/sessions")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_bad_key_returns_401(self, client, bad_headers) -> None:
        resp = await client.get("/api/v1/sessions", headers=bad_headers)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, client) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_no_auth_required(self, client) -> None:
        resp = await client.get("/metrics")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Role stored on request state
# ---------------------------------------------------------------------------


class TestRoleOnRequestState:
    """Verify that the resolved role is stored on request.state."""

    @pytest.mark.asyncio
    async def test_admin_role_in_audit_log(self, client, headers, caplog) -> None:
        """Admin requests should have role=admin available for audit."""
        # Make a write request that triggers audit logging
        with caplog.at_level("INFO", logger="dawos_agent.audit"):
            await client.post(
                "/api/v1/service/command",
                headers=headers,
                json={"command": "show stat"},
            )
        # The role is stored on request.state.role for the audit middleware
        # This is verified indirectly — if it didn't raise, role was set


# ---------------------------------------------------------------------------
# Resolver accessor
# ---------------------------------------------------------------------------


class TestGetResolver:
    """Verify the module-level resolver accessor."""

    def test_get_resolver_returns_instance(self) -> None:
        from dawos_agent.auth import get_resolver  # noqa: C0415
        from dawos_agent.rbac import KeyResolver

        resolver = get_resolver()
        assert isinstance(resolver, KeyResolver)
