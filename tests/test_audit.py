"""Tests for the audit log middleware."""

from __future__ import annotations

import logging

import pytest


@pytest.mark.asyncio
async def test_audit_logs_post_request(client, headers, caplog):
    """POST requests should produce an audit log entry."""
    with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
        resp = await client.post(
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
async def test_audit_logs_delete_request(client, headers, caplog):
    """DELETE requests should produce an audit log entry."""
    with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
        resp = await client.delete(
            "/api/v1/firewall/groups/test-nonexistent",
            headers=headers,
        )
    audit_entries = [r for r in caplog.records if r.name == "dawos_agent.audit"]
    assert len(audit_entries) >= 1
    assert "method=DELETE" in audit_entries[0].message


@pytest.mark.asyncio
async def test_audit_skips_get_request(client, caplog):
    """GET requests should NOT produce audit log entries."""
    with caplog.at_level(logging.INFO, logger="dawos_agent.audit"):
        await client.get("/health")
    audit_entries = [r for r in caplog.records if r.name == "dawos_agent.audit"]
    assert len(audit_entries) == 0


@pytest.mark.asyncio
async def test_audit_includes_request_id(client, headers, caplog):
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
async def test_audit_logs_put_request(client, headers, caplog):
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
