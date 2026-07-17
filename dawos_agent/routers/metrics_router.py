"""Prometheus metrics exposition endpoint.

Serves the ``/metrics`` endpoint in Prometheus text exposition format.

By default this endpoint is **public** (no API key required) following
the standard convention for metrics scraping — Prometheus, Grafana
Agent, and other collectors typically do not support custom
authentication headers.

When ``DAWOS_METRICS_AUTH=true`` is set, the endpoint requires a valid
``X-API-Key`` header (viewer role or above).  Configure Prometheus with
``authorization`` or ``bearer_token_file`` in that case (DAWOS-14).

The endpoint is also exempt from rate limiting to ensure reliable
metric collection at any scrape interval.

Usage with Prometheus::

    # prometheus.yml
    scrape_configs:
      - job_name: dawos-agent
        scrape_interval: 15s
        static_configs:
          - targets: ['bng-node-01:8470']

    # When DAWOS_METRICS_AUTH=true, add:
    #   authorization:
    #     credentials: '<your-api-key>'
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.security import APIKeyHeader
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..config import settings
from ..middleware import limiter

router = APIRouter(tags=["metrics"])

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@router.get(
    "/metrics",
    response_class=Response,
    summary="Prometheus metrics",
    description="Returns all collected metrics in Prometheus text exposition format.",
)
@limiter.exempt
async def prometheus_metrics(request: Request):
    """Expose collected metrics in Prometheus text exposition format.

    Returns all registered metrics (HTTP request counters, latency
    histograms, accel-cmd error counters, retry counters, and rate
    limit rejection counters) as a plain-text response compatible with
    Prometheus, Grafana Agent, Victoria Metrics, and other collectors.

    When ``settings.metrics_auth`` is enabled, a valid ``X-API-Key``
    header is required (viewer role or above).

    Returns:
        Response: Plain text body with ``text/plain`` content type and
        Prometheus version parameter.
    """
    if settings.metrics_auth:
        from ..auth import get_resolver  # pylint: disable=import-outside-toplevel

        key = request.headers.get("x-api-key")
        resolver = get_resolver()
        if not key or resolver.resolve(key) is None:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
