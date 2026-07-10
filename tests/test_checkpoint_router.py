"""Tests for routers/checkpoint.py — config checkpoint endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_revisions(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.list_backups",
        return_value=[
            {
                "name": "accel-ppp.conf.20250101_120000.bak",
                "size": 100,
                "created": "2025-01-01T12:00:00",
                "path": "/tmp/a",
            },
            {
                "name": "accel-ppp.conf.20250102_120000.checkpoint",
                "size": 200,
                "created": "2025-01-02T12:00:00",
                "path": "/tmp/b",
            },
        ],
    ):
        resp = await client.get(
            "/api/v1/config/revisions",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["revisions"][0]["is_checkpoint"] is False
    assert data["revisions"][1]["is_checkpoint"] is True


@pytest.mark.asyncio
async def test_list_revisions_empty(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.list_backups",
        return_value=[],
    ):
        resp = await client.get(
            "/api/v1/config/revisions",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["count"] == 0


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_revision(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.diff_with_backup",
        return_value={"diff": "-old\n+new\n", "changed": True},
    ):
        resp = await client.get(
            "/api/v1/config/diff",
            params={"backup_name": "accel-ppp.conf.20250101_120000.bak"},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["changed"] is True
    assert "-old" in data["diff"]


@pytest.mark.asyncio
async def test_diff_revision_not_found(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.diff_with_backup",
        side_effect=FileNotFoundError("not found"),
    ):
        resp = await client.get(
            "/api/v1/config/diff",
            params={"backup_name": "missing.bak"},
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_diff_revision_error(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.diff_with_backup",
        side_effect=Exception("fail"),
    ):
        resp = await client.get(
            "/api/v1/config/diff",
            params={"backup_name": "crash.bak"},
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.rollback_to",
        return_value="/backups/safety.bak",
    ):
        resp = await client.post(
            "/api/v1/config/rollback/accel-ppp.conf.20250101_120000.bak",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "rolled back" in data["message"].lower()


@pytest.mark.asyncio
async def test_rollback_not_found(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.rollback_to",
        side_effect=FileNotFoundError("not found"),
    ):
        resp = await client.post(
            "/api/v1/config/rollback/missing.bak",
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rollback_error(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.rollback_to",
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/config/rollback/crash.bak",
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Guarded apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guarded_apply(client, headers):
    with (
        patch(
            "dawos_agent.routers.checkpoint.config_manager.create_checkpoint",
            return_value="/backups/cp.checkpoint",
        ),
        patch(
            "dawos_agent.routers.checkpoint.config_manager.write_config",
            return_value="/backups/pre.bak",
        ),
        patch(
            "dawos_agent.routers.checkpoint.config_manager.start_guarded_timer",
        ),
        patch(
            "dawos_agent.routers.checkpoint.accel.reload_config",
            new_callable=AsyncMock,
        ),
    ):
        resp = await client.post(
            "/api/v1/config/apply",
            json={"content": "[ppp]\nnew=1\n", "confirm_minutes": 5},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["confirm_deadline_seconds"] == 300
    assert "confirm" in data["message"].lower()


@pytest.mark.asyncio
async def test_guarded_apply_rejects_whitespace_only(client, headers):
    resp = await client.post(
        "/api/v1/config/apply",
        json={"content": "              ", "confirm_minutes": 5},
        headers=headers,
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_guarded_apply_rejects_no_section_header(client, headers):
    resp = await client.post(
        "/api/v1/config/apply",
        json={"content": "just some random text without headers", "confirm_minutes": 5},
        headers=headers,
    )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_guarded_apply_error(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.create_checkpoint",
        side_effect=Exception("disk full"),
    ):
        resp = await client.post(
            "/api/v1/config/apply",
            json={"content": "[ppp]\nkey=value\n", "confirm_minutes": 5},
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Confirm apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_apply(client, headers):
    with (
        patch(
            "dawos_agent.routers.checkpoint.config_manager.guarded_apply_status",
            return_value={"pending": True, "checkpoint": "/tmp/cp"},
        ),
        patch(
            "dawos_agent.routers.checkpoint.config_manager.cancel_guarded_timer",
        ),
    ):
        resp = await client.post(
            "/api/v1/config/confirm",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "confirmed" in data["message"].lower()


@pytest.mark.asyncio
async def test_confirm_apply_no_pending(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.guarded_apply_status",
        return_value={"pending": False, "checkpoint": None},
    ):
        resp = await client.post(
            "/api/v1/config/confirm",
            headers=headers,
        )

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Apply status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_status_pending(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.guarded_apply_status",
        return_value={"pending": True, "checkpoint": "/tmp/cp"},
    ):
        resp = await client.get(
            "/api/v1/config/apply/status",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["pending"] is True


@pytest.mark.asyncio
async def test_apply_status_idle(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.guarded_apply_status",
        return_value={"pending": False, "checkpoint": None},
    ):
        resp = await client.get(
            "/api/v1/config/apply/status",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["pending"] is False


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkpoint_requires_auth(client, bad_headers):
    resp = await client.get(
        "/api/v1/config/revisions",
        headers=bad_headers,
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Revision content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revision_content(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.read_backup",
        return_value=("[ppp]\nverbose=1\n", 18, "2025-01-01T12:00:00"),
    ):
        resp = await client.get(
            "/api/v1/config/revisions/accel-ppp.conf.20250101_120000.bak/content",
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "accel-ppp.conf.20250101_120000.bak"
    assert data["size"] == 18
    assert data["created"] == "2025-01-01T12:00:00"
    assert "[ppp]" in data["content"]


@pytest.mark.asyncio
async def test_revision_content_not_found(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.read_backup",
        side_effect=FileNotFoundError("not found"),
    ):
        resp = await client.get(
            "/api/v1/config/revisions/missing.bak/content",
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revision_content_checkpoint(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.read_backup",
        return_value=("[modules]\n", 10, "2025-01-02T08:00:00"),
    ):
        resp = await client.get(
            "/api/v1/config/revisions/accel-ppp.conf.20250102_080000.checkpoint/content",
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["size"] == 10


# ---------------------------------------------------------------------------
# Compare two revisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_revisions(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.diff_two_revisions",
        return_value={
            "from_name": "a.bak",
            "to_name": "b.bak",
            "diff": "-old\n+new\n",
            "changed": True,
        },
    ):
        resp = await client.get(
            "/api/v1/config/compare",
            params={"from_name": "a.bak", "to_name": "b.bak"},
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["from_name"] == "a.bak"
    assert data["to_name"] == "b.bak"
    assert data["changed"] is True
    assert "-old" in data["diff"]


@pytest.mark.asyncio
async def test_compare_revisions_identical(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.diff_two_revisions",
        return_value={
            "from_name": "a.bak",
            "to_name": "b.bak",
            "diff": "",
            "changed": False,
        },
    ):
        resp = await client.get(
            "/api/v1/config/compare",
            params={"from_name": "a.bak", "to_name": "b.bak"},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["changed"] is False


@pytest.mark.asyncio
async def test_compare_revisions_not_found(client, headers):
    with patch(
        "dawos_agent.routers.checkpoint.config_manager.diff_two_revisions",
        side_effect=FileNotFoundError("Revision not found: missing.bak"),
    ):
        resp = await client.get(
            "/api/v1/config/compare",
            params={"from_name": "missing.bak", "to_name": "b.bak"},
            headers=headers,
        )

    assert resp.status_code == 404
    assert "missing.bak" in resp.json()["detail"]
