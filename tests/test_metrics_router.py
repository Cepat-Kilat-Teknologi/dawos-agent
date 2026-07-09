"""Tests for the Prometheus metrics exposition endpoint."""

from __future__ import annotations

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
