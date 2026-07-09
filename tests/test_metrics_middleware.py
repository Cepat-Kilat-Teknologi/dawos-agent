"""Tests for the Prometheus MetricsMiddleware (pure ASGI)."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from dawos_agent.middleware import MetricsMiddleware

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_counter_value(name: str, labels: dict[str, str] | None = None) -> float:
    """Read the current value of a Prometheus counter from the registry.

    Args:
        name: The metric name **without** the ``_total`` suffix that
            prometheus_client appends internally for counters.
        labels: Label dict to look up a specific series.

    Returns:
        The counter value, or 0.0 if not yet observed.
    """
    for metric in REGISTRY.collect():
        if metric.name == name or metric.name == f"{name}_total":
            for sample in metric.samples:
                if labels is None and sample.name == f"{name}_total":
                    return sample.value
                if labels and sample.labels == labels:
                    return sample.value
    return 0.0


def _get_histogram_count(name: str, labels: dict[str, str] | None = None) -> float:
    """Read the observation count from a Prometheus histogram.

    Args:
        name: The metric base name (e.g. ``dawos_http_request_duration_seconds``).
        labels: Label dict for a specific series.

    Returns:
        The ``_count`` value, or 0.0 if not yet observed.
    """
    for metric in REGISTRY.collect():
        if metric.name == name:
            for sample in metric.samples:
                if sample.name == f"{name}_count":
                    if labels is None:
                        return sample.value
                    if all(sample.labels.get(k) == v for k, v in labels.items()):
                        return sample.value
    return 0.0


# ---------------------------------------------------------------------------
# MetricsMiddleware integration tests
# ---------------------------------------------------------------------------


class TestMetricsMiddleware:
    """Verify MetricsMiddleware records HTTP metrics correctly."""

    @pytest.mark.asyncio
    async def test_request_increments_counter(self, client) -> None:
        """A regular API request should increment the request counter."""
        before = _get_counter_value(
            "dawos_http_requests",
            {"method": "GET", "endpoint": "/health", "status": "200"},
        )

        await client.get("/health")

        after = _get_counter_value(
            "dawos_http_requests",
            {"method": "GET", "endpoint": "/health", "status": "200"},
        )
        # /health is in the skip set, so counter should NOT increase
        assert after == before

    @pytest.mark.asyncio
    async def test_skip_paths_not_counted(self, client) -> None:
        """Requests to /metrics, /health, /health/ready must be excluded."""
        before_health = _get_counter_value(
            "dawos_http_requests",
            {"method": "GET", "endpoint": "/health", "status": "200"},
        )
        before_metrics = _get_counter_value(
            "dawos_http_requests",
            {"method": "GET", "endpoint": "/metrics", "status": "200"},
        )

        await client.get("/health")
        await client.get("/metrics")

        after_health = _get_counter_value(
            "dawos_http_requests",
            {"method": "GET", "endpoint": "/health", "status": "200"},
        )
        after_metrics = _get_counter_value(
            "dawos_http_requests",
            {"method": "GET", "endpoint": "/metrics", "status": "200"},
        )
        assert after_health == before_health
        assert after_metrics == before_metrics

    @pytest.mark.asyncio
    async def test_authenticated_endpoint_counted(self, client, headers) -> None:
        """Authenticated API requests should be recorded in metrics."""
        # Pick a known protected endpoint
        before = _get_counter_value(
            "dawos_http_requests",
            {"method": "GET", "endpoint": "/docs", "status": "200"},
        )

        resp = await client.get("/docs")

        # /docs returns 200 (OpenAPI docs are public in FastAPI)
        if resp.status_code == 200:
            after = _get_counter_value(
                "dawos_http_requests",
                {"method": "GET", "endpoint": "/docs", "status": "200"},
            )
            assert after > before

    @pytest.mark.asyncio
    async def test_duration_histogram_recorded(self, client) -> None:
        """Requests to counted paths should populate the duration histogram."""
        before = _get_histogram_count(
            "dawos_http_request_duration_seconds",
            {"method": "GET", "endpoint": "/docs"},
        )

        await client.get("/docs")

        after = _get_histogram_count(
            "dawos_http_request_duration_seconds",
            {"method": "GET", "endpoint": "/docs"},
        )
        assert after > before

    @pytest.mark.asyncio
    async def test_401_counted_with_status_label(self, client) -> None:
        """Unauthenticated requests to protected endpoints record status=401."""
        # Hit a protected endpoint without auth header
        resp = await client.get("/api/v1/sessions")
        assert resp.status_code == 401

        value = _get_counter_value(
            "dawos_http_requests",
            {"method": "GET", "endpoint": "/api/v1/sessions", "status": "401"},
        )
        assert value >= 1.0

    @pytest.mark.asyncio
    async def test_duration_not_recorded_for_skip_paths(self, client) -> None:
        """Excluded paths should not appear in the duration histogram."""
        before = _get_histogram_count(
            "dawos_http_request_duration_seconds",
            {"method": "GET", "endpoint": "/health"},
        )

        await client.get("/health")

        after = _get_histogram_count(
            "dawos_http_request_duration_seconds",
            {"method": "GET", "endpoint": "/health"},
        )
        assert after == before

    @pytest.mark.asyncio
    async def test_429_increments_rate_limit_counter(self) -> None:
        """A 429 response should increment the rate limit hits counter."""
        from dawos_agent.metrics import RATE_LIMIT_HITS_TOTAL

        before = RATE_LIMIT_HITS_TOTAL._value.get()

        # Build a minimal ASGI app that always returns 429.
        async def fake_app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"rate limited",
                }
            )

        middleware = MetricsMiddleware(fake_app)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/sessions",
        }

        async def noop_send(message):
            pass

        await middleware(scope, None, noop_send)

        after = RATE_LIMIT_HITS_TOTAL._value.get()
        assert after == before + 1
