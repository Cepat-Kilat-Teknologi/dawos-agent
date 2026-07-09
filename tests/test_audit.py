"""Tests for the audit log middleware, ring buffer, and audit API endpoint."""

from __future__ import annotations

import logging

import pytest

from dawos_agent.middleware import audit_buffer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clear_buffer():
    """Clear the global audit buffer between tests."""
    audit_buffer.clear()


# ---------------------------------------------------------------------------
# Audit logging (existing coverage, updated for role field)
# ---------------------------------------------------------------------------


class TestAuditLogging:
    """Verify audit log messages for mutating requests."""

    @pytest.mark.asyncio
    async def test_audit_logs_post_request(self, client, headers, caplog) -> None:
        """POST requests should produce an audit log entry."""
        with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
            await client.post(
                "/api/v1/sessions/terminate",
                headers=headers,
                json={"username": "test-user"},
            )
        audit_entries = [r for r in caplog.records if r.name == "dawos_agent.audit"]
        assert len(audit_entries) >= 1
        msg = audit_entries[0].message
        assert "method=POST" in msg
        assert "path=/api/v1/sessions/terminate" in msg
        assert "status=" in msg
        assert "duration_ms=" in msg

    @pytest.mark.asyncio
    async def test_audit_logs_delete_request(self, client, headers, caplog) -> None:
        """DELETE requests should produce an audit log entry."""
        with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
            await client.delete(
                "/api/v1/firewall/groups/test-nonexistent",
                headers=headers,
            )
        audit_entries = [r for r in caplog.records if r.name == "dawos_agent.audit"]
        assert len(audit_entries) >= 1
        assert "method=DELETE" in audit_entries[0].message

    @pytest.mark.asyncio
    async def test_audit_skips_get_request(self, client, caplog) -> None:
        """GET requests should NOT produce audit log entries."""
        with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
            await client.get("/health")
        audit_entries = [r for r in caplog.records if r.name == "dawos_agent.audit"]
        assert len(audit_entries) == 0

    @pytest.mark.asyncio
    async def test_audit_includes_request_id(self, client, headers, caplog) -> None:
        """Audit entries should include the request trace ID."""
        custom_id = "audit-trace-999"
        with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
            await client.put(
                "/api/v1/config",
                headers={**headers, "X-Request-ID": custom_id},
                json={"content": "# test config content for audit"},
            )
        audit_entries = [r for r in caplog.records if r.name == "dawos_agent.audit"]
        assert len(audit_entries) >= 1
        assert f"request_id={custom_id}" in audit_entries[0].message

    @pytest.mark.asyncio
    async def test_audit_logs_put_request(self, client, headers, caplog) -> None:
        """PUT requests should produce an audit log entry."""
        with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
            await client.put(
                "/api/v1/config",
                headers=headers,
                json={"content": "# minimal config content test"},
            )
        audit_entries = [r for r in caplog.records if r.name == "dawos_agent.audit"]
        assert len(audit_entries) >= 1
        assert "method=PUT" in audit_entries[0].message

    @pytest.mark.asyncio
    async def test_audit_includes_role(self, client, headers, caplog) -> None:
        """Audit entries should include the RBAC role of the caller."""
        with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
            await client.post(
                "/api/v1/service/command",
                headers=headers,
                json={"command": "show stat"},
            )
        audit_entries = [r for r in caplog.records if r.name == "dawos_agent.audit"]
        assert len(audit_entries) >= 1
        assert "role=admin" in audit_entries[0].message


# ---------------------------------------------------------------------------
# Ring buffer population
# ---------------------------------------------------------------------------


class TestAuditBuffer:
    """Verify that mutating requests populate the in-memory ring buffer."""

    @pytest.mark.asyncio
    async def test_post_populates_buffer(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        assert len(audit_buffer) == 1
        entry = audit_buffer[0]
        assert entry["method"] == "POST"
        assert entry["path"] == "/api/v1/service/command"
        assert entry["role"] == "admin"
        assert "timestamp" in entry
        assert "request_id" in entry

    @pytest.mark.asyncio
    async def test_get_does_not_populate_buffer(self, client, headers) -> None:
        _clear_buffer()
        await client.get("/api/v1/sessions", headers=headers)
        assert len(audit_buffer) == 0

    @pytest.mark.asyncio
    async def test_buffer_records_operator_role(
        self,
        client,
        operator_headers,
    ) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/sessions/terminate",
            headers=operator_headers,
            json={"username": "test"},
        )
        assert len(audit_buffer) == 1
        assert audit_buffer[0]["role"] == "operator"

    @pytest.mark.asyncio
    async def test_buffer_has_maxlen(self) -> None:
        assert audit_buffer.maxlen is not None
        assert audit_buffer.maxlen > 0

    @pytest.mark.asyncio
    async def test_multiple_requests_ordered(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        await client.post(
            "/api/v1/sessions/terminate",
            headers=headers,
            json={"username": "test"},
        )
        assert len(audit_buffer) == 2
        assert audit_buffer[0]["path"] == "/api/v1/service/command"
        assert audit_buffer[1]["path"] == "/api/v1/sessions/terminate"

    @pytest.mark.asyncio
    async def test_entry_has_duration(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        assert audit_buffer[0]["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# Audit API endpoint
# ---------------------------------------------------------------------------


class TestAuditEndpoint:
    """Verify GET /api/v1/audit endpoint behaviour."""

    @pytest.mark.asyncio
    async def test_admin_can_access_audit(self, client, admin_headers) -> None:
        resp = await client.get("/api/v1/audit", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "count" in body
        assert "buffer_size" in body
        assert "entries" in body

    @pytest.mark.asyncio
    async def test_viewer_cannot_access_audit(self, client, viewer_headers) -> None:
        resp = await client.get("/api/v1/audit", headers=viewer_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_cannot_access_audit(
        self,
        client,
        operator_headers,
    ) -> None:
        resp = await client.get("/api/v1/audit", headers=operator_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, client) -> None:
        resp = await client.get("/api/v1/audit")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_entries_newest_first(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        await client.post(
            "/api/v1/sessions/terminate",
            headers=headers,
            json={"username": "test"},
        )
        resp = await client.get("/api/v1/audit", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["entries"][0]["path"] == "/api/v1/sessions/terminate"
        assert body["entries"][1]["path"] == "/api/v1/service/command"

    @pytest.mark.asyncio
    async def test_filter_by_method(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        resp = await client.get(
            "/api/v1/audit",
            headers=headers,
            params={"method": "POST"},
        )
        body = resp.json()
        assert body["count"] >= 1
        assert all(e["method"] == "POST" for e in body["entries"])

    @pytest.mark.asyncio
    async def test_filter_by_path(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        resp = await client.get(
            "/api/v1/audit",
            headers=headers,
            params={"path": "/api/v1/service"},
        )
        body = resp.json()
        assert body["count"] >= 1
        assert all(e["path"].startswith("/api/v1/service") for e in body["entries"])

    @pytest.mark.asyncio
    async def test_filter_by_role(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        resp = await client.get(
            "/api/v1/audit",
            headers=headers,
            params={"role": "admin"},
        )
        body = resp.json()
        assert body["count"] >= 1
        assert all(e["role"] == "admin" for e in body["entries"])

    @pytest.mark.asyncio
    async def test_filter_by_status(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        resp = await client.get(
            "/api/v1/audit",
            headers=headers,
            params={"status": 500},
        )
        body = resp.json()
        assert all(e["status"] == 500 for e in body["entries"])

    @pytest.mark.asyncio
    async def test_limit_parameter(self, client, headers) -> None:
        _clear_buffer()
        for _ in range(3):
            await client.post(
                "/api/v1/service/command",
                headers=headers,
                json={"command": "show stat"},
            )
        resp = await client.get(
            "/api/v1/audit",
            headers=headers,
            params={"limit": 2},
        )
        body = resp.json()
        assert body["count"] == 2

    @pytest.mark.asyncio
    async def test_buffer_size_in_response(self, client, headers) -> None:
        resp = await client.get("/api/v1/audit", headers=headers)
        body = resp.json()
        assert body["buffer_size"] == 1000

    @pytest.mark.asyncio
    async def test_entry_fields_complete(self, client, headers) -> None:
        _clear_buffer()
        await client.post(
            "/api/v1/service/command",
            headers=headers,
            json={"command": "show stat"},
        )
        resp = await client.get("/api/v1/audit", headers=headers)
        body = resp.json()
        entry = body["entries"][0]
        expected_fields = {
            "timestamp",
            "method",
            "path",
            "client_ip",
            "request_id",
            "role",
            "status",
            "duration_ms",
        }
        assert expected_fields == set(entry.keys())
