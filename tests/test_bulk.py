"""Tests for the bulk operations API and service layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bulk terminate
# ---------------------------------------------------------------------------


class TestBulkTerminate:
    """Verify POST /api/v1/bulk/terminate endpoint."""

    @pytest.mark.asyncio
    async def test_terminate_all_success(self, client, headers) -> None:
        with patch(
            "dawos_agent.services.bulk.accel.terminate_session",
            new_callable=AsyncMock,
            return_value="OK",
        ):
            resp = await client.post(
                "/api/v1/bulk/terminate",
                json={"usernames": ["user1", "user2", "user3"]},
                headers=headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["operation"] == "terminate"
        assert body["total"] == 3
        assert body["succeeded"] == 3
        assert body["failed"] == 0
        assert len(body["results"]) == 3
        assert all(r["success"] for r in body["results"])

    @pytest.mark.asyncio
    async def test_terminate_partial_failure(self, client, headers) -> None:
        side = [
            "OK",
            RuntimeError("No active session"),
            "OK",
        ]
        with patch(
            "dawos_agent.services.bulk.accel.terminate_session",
            new_callable=AsyncMock,
            side_effect=side,
        ):
            resp = await client.post(
                "/api/v1/bulk/terminate",
                json={"usernames": ["user1", "user2", "user3"]},
                headers=headers,
            )
        body = resp.json()
        assert body["succeeded"] == 2
        assert body["failed"] == 1
        assert body["results"][1]["success"] is False
        assert "No active session" in body["results"][1]["message"]

    @pytest.mark.asyncio
    async def test_terminate_all_fail(self, client, headers) -> None:
        with patch(
            "dawos_agent.services.bulk.accel.terminate_session",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Connection refused"),
        ):
            resp = await client.post(
                "/api/v1/bulk/terminate",
                json={"usernames": ["user1"]},
                headers=headers,
            )
        body = resp.json()
        assert body["succeeded"] == 0
        assert body["failed"] == 1

    @pytest.mark.asyncio
    async def test_terminate_empty_list_rejected(self, client, headers) -> None:
        resp = await client.post(
            "/api/v1/bulk/terminate",
            json={"usernames": []},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_terminate_invalid_username_rejected(
        self,
        client,
        headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/bulk/terminate",
            json={"usernames": ["valid", "not valid!"]},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_terminate_viewer_forbidden(
        self,
        client,
        viewer_headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/bulk/terminate",
            json={"usernames": ["user1"]},
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_terminate_no_auth(self, client) -> None:
        resp = await client.post(
            "/api/v1/bulk/terminate",
            json={"usernames": ["user1"]},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Bulk ratelimit
# ---------------------------------------------------------------------------


class TestBulkRateLimit:
    """Verify POST /api/v1/bulk/ratelimit endpoint."""

    @pytest.mark.asyncio
    async def test_ratelimit_all_success(self, client, headers) -> None:
        with patch(
            "dawos_agent.services.bulk.traffic.change_ratelimit",
            new_callable=AsyncMock,
            return_value="Shaper changed",
        ):
            resp = await client.post(
                "/api/v1/bulk/ratelimit",
                json={
                    "items": [
                        {"username": "user1", "rate": "10M/20M"},
                        {"username": "user2", "rate": "5M/10M"},
                    ],
                },
                headers=headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["operation"] == "ratelimit"
        assert body["total"] == 2
        assert body["succeeded"] == 2
        assert body["failed"] == 0

    @pytest.mark.asyncio
    async def test_ratelimit_partial_failure(self, client, headers) -> None:
        side = [
            "Shaper changed",
            ValueError("No live session for user2"),
        ]
        with patch(
            "dawos_agent.services.bulk.traffic.change_ratelimit",
            new_callable=AsyncMock,
            side_effect=side,
        ):
            resp = await client.post(
                "/api/v1/bulk/ratelimit",
                json={
                    "items": [
                        {"username": "user1", "rate": "10M/20M"},
                        {"username": "user2", "rate": "5M/10M"},
                    ],
                },
                headers=headers,
            )
        body = resp.json()
        assert body["succeeded"] == 1
        assert body["failed"] == 1
        assert body["results"][0]["success"] is True
        assert body["results"][1]["success"] is False

    @pytest.mark.asyncio
    async def test_ratelimit_empty_items_rejected(
        self,
        client,
        headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/bulk/ratelimit",
            json={"items": []},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ratelimit_invalid_rate_rejected(
        self,
        client,
        headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/bulk/ratelimit",
            json={"items": [{"username": "user1", "rate": "bad"}]},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_ratelimit_viewer_forbidden(
        self,
        client,
        viewer_headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/bulk/ratelimit",
            json={"items": [{"username": "u", "rate": "1M/1M"}]},
            headers=viewer_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Bulk shaper restore
# ---------------------------------------------------------------------------


class TestBulkShaperRestore:
    """Verify POST /api/v1/bulk/shaper-restore endpoint."""

    @pytest.mark.asyncio
    async def test_restore_all_success(self, client, headers) -> None:
        with patch(
            "dawos_agent.services.bulk.traffic.restore_ratelimit",
            new_callable=AsyncMock,
            return_value="Shaper restored",
        ):
            resp = await client.post(
                "/api/v1/bulk/shaper-restore",
                json={"usernames": ["user1", "user2"]},
                headers=headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["operation"] == "shaper-restore"
        assert body["total"] == 2
        assert body["succeeded"] == 2

    @pytest.mark.asyncio
    async def test_restore_partial_failure(self, client, headers) -> None:
        side = [
            "Shaper restored",
            ValueError("No live session"),
        ]
        with patch(
            "dawos_agent.services.bulk.traffic.restore_ratelimit",
            new_callable=AsyncMock,
            side_effect=side,
        ):
            resp = await client.post(
                "/api/v1/bulk/shaper-restore",
                json={"usernames": ["user1", "user2"]},
                headers=headers,
            )
        body = resp.json()
        assert body["succeeded"] == 1
        assert body["failed"] == 1

    @pytest.mark.asyncio
    async def test_restore_empty_list_rejected(
        self,
        client,
        headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/bulk/shaper-restore",
            json={"usernames": []},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_restore_invalid_username_rejected(
        self,
        client,
        headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/bulk/shaper-restore",
            json={"usernames": ["ok", "not ok!"]},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_restore_no_auth(self, client) -> None:
        resp = await client.post(
            "/api/v1/bulk/shaper-restore",
            json={"usernames": ["user1"]},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------


class TestBulkResponseStructure:
    """Verify bulk response fields conform to schema."""

    @pytest.mark.asyncio
    async def test_result_item_has_required_fields(
        self,
        client,
        headers,
    ) -> None:
        with patch(
            "dawos_agent.services.bulk.accel.terminate_session",
            new_callable=AsyncMock,
            return_value="OK",
        ):
            resp = await client.post(
                "/api/v1/bulk/terminate",
                json={"usernames": ["testuser"]},
                headers=headers,
            )
        body = resp.json()
        for result in body["results"]:
            assert "target" in result
            assert "success" in result
            assert "message" in result

    @pytest.mark.asyncio
    async def test_response_has_counts(self, client, headers) -> None:
        with patch(
            "dawos_agent.services.bulk.accel.terminate_session",
            new_callable=AsyncMock,
            return_value="OK",
        ):
            resp = await client.post(
                "/api/v1/bulk/terminate",
                json={"usernames": ["a"]},
                headers=headers,
            )
        body = resp.json()
        assert "operation" in body
        assert "total" in body
        assert "succeeded" in body
        assert "failed" in body
        assert "results" in body
