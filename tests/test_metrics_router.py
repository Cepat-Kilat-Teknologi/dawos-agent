"""Tests for the Prometheus metrics exposition endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    """Tests for the ``GET /metrics`` endpoint."""

    @pytest.mark.asyncio
    async def test_returns_200(self, client) -> None:
        """The metrics endpoint should return HTTP 200."""
        resp = await client.get("/metrics")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_auth_required(self, client) -> None:
        """Metrics endpoint must be accessible without an API key."""
        resp = await client.get("/metrics")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_content_type_is_prometheus(self, client) -> None:
        """Response Content-Type must match Prometheus text format."""
        resp = await client.get("/metrics")
        ct = resp.headers["content-type"]
        assert "text/plain" in ct

    @pytest.mark.asyncio
    async def test_body_contains_default_metrics(self, client) -> None:
        """Response body should include at least the default process metrics."""
        resp = await client.get("/metrics")
        body = resp.text
        # prometheus_client always exposes process and Python info collectors
        assert "python_info" in body or "process_" in body or "dawos_" in body

    @pytest.mark.asyncio
    async def test_body_contains_custom_metrics(self, client) -> None:
        """Response body should contain the dawos-agent custom metric names."""
        resp = await client.get("/metrics")
        body = resp.text
        # At minimum the HELP/TYPE lines for registered metrics appear
        assert "dawos_http_requests_total" in body or "dawos_http_requests" in body

    @pytest.mark.asyncio
    async def test_metrics_exempt_from_rate_limit(self, client) -> None:
        """Rapid repeated requests to /metrics should never be rate-limited."""
        for _ in range(10):
            resp = await client.get("/metrics")
            assert resp.status_code == 200


class TestMetricsAuth:
    """Tests for optional DAWOS_METRICS_AUTH guarding (DAWOS-14)."""

    @pytest.mark.asyncio
    async def test_metrics_auth_rejects_without_key(self, client) -> None:
        """When metrics_auth is enabled, requests without API key get 401."""
        with patch("dawos_agent.routers.metrics_router.settings") as mock_cfg:
            mock_cfg.metrics_auth = True
            resp = await client.get("/metrics")
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_metrics_auth_rejects_bad_key(self, client) -> None:
        """When metrics_auth is enabled, an invalid key returns 401."""
        with patch("dawos_agent.routers.metrics_router.settings") as mock_cfg:
            mock_cfg.metrics_auth = True
            resp = await client.get("/metrics", headers={"X-API-Key": "wrong-key"})
            assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_metrics_auth_accepts_valid_key(self, client, headers) -> None:
        """When metrics_auth is enabled, a valid key returns 200."""
        with patch("dawos_agent.routers.metrics_router.settings") as mock_cfg:
            mock_cfg.metrics_auth = True
            resp = await client.get("/metrics", headers=headers)
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_metrics_no_auth_by_default(self, client) -> None:
        """Default settings.metrics_auth=False allows unauthenticated access."""
        resp = await client.get("/metrics")
        assert resp.status_code == 200
