"""Tests for config validation endpoint in config_router.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# POST /config/validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_config_valid(client, headers):
    """Valid config returns valid=True."""
    body = {"content": "[modules]\nlog_file\n\n[core]\nthread-count=4\n"}
    resp = await client.post("/api/v1/config/validate", json=body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["errors"] == 0
    assert "modules" in data["sections"]


@pytest.mark.asyncio
async def test_validate_config_invalid(client, headers):
    """Config missing [modules] returns valid=False."""
    body = {"content": "[core]\nthread-count=4\n"}
    resp = await client.post("/api/v1/config/validate", json=body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert data["errors"] >= 1


@pytest.mark.asyncio
async def test_validate_config_with_issues(client, headers):
    """Config with warnings returns issues list."""
    body = {"content": ("[modules]\nlog_file\n\n[core]\nbare_key\nthread-count=4\n")}
    resp = await client.post("/api/v1/config/validate", json=body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["warnings"] >= 1
    assert len(data["issues"]) >= 1


@pytest.mark.asyncio
async def test_validate_config_error(client, headers):
    """Internal error returns 500."""
    with patch(
        "dawos_agent.routers.config_router.config_validator.validate_config",
        side_effect=Exception("boom"),
    ):
        body = {"content": "[modules]\nlog_file\n"}
        resp = await client.post("/api/v1/config/validate", json=body, headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_validate_config_empty_body(client, headers):
    """Empty content rejected by Pydantic validation (422)."""
    body = {"content": ""}
    resp = await client.post("/api/v1/config/validate", json=body, headers=headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_config_requires_auth(client, bad_headers):
    """Validate endpoint requires authentication."""
    body = {"content": "[modules]\nlog_file\n"}
    resp = await client.post("/api/v1/config/validate", json=body, headers=bad_headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Model smoke tests
# ---------------------------------------------------------------------------


def test_config_validation_issue_defaults():
    from dawos_agent.models.schemas import ConfigValidationIssue

    obj = ConfigValidationIssue()
    assert obj.severity == "error"
    assert obj.line == 0
    assert obj.section == ""
    assert obj.message == ""


def test_config_validation_request_defaults():
    from dawos_agent.models.schemas import ConfigValidationRequest

    obj = ConfigValidationRequest(content="test")
    assert obj.content == "test"


def test_config_validation_response_defaults():
    from dawos_agent.models.schemas import ConfigValidationResponse

    obj = ConfigValidationResponse()
    assert obj.valid is True
    assert obj.errors == 0
    assert obj.warnings == 0
    assert obj.sections == []
    assert obj.issues == []
