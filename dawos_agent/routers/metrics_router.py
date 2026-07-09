"""Prometheus metrics exposition endpoint.

Serves the ``/metrics`` endpoint in Prometheus text exposition format.
This endpoint is **public** (no API key required) following the standard
convention for metrics scraping — Prometheus, Grafana Agent, and other
collectors typically do not support custom authentication headers.

The endpoint is also exempt from rate limiting to ensure reliable
metric collection at any scrape interval.

Usage with Prometheus::

    # prometheus.yml
    scrape_configs:
      - job_name: dawos-agent
        scrape_interval: 15s
        static_configs:
          - targets: ['bng-node-01:8470']
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ..middleware import limiter

router = APIRouter(tags=["metrics"])


@router.get(
    "/metrics",
    response_class=Response,
    summary="Prometheus metrics",
    description="Returns all collected metrics in Prometheus text exposition format.",
)
@limiter.exempt
async def prometheus_metrics():
    """Expose collected metrics in Prometheus text exposition format.

    Returns all registered metrics (HTTP request counters, latency
    histograms, accel-cmd error counters, retry counters, and rate
    limit rejection counters) as a plain-text response compatible with
    Prometheus, Grafana Agent, Victoria Metrics, and other collectors.

    No authentication is required.  Rate limiting is exempt.

    Returns:
        Response: Plain text body with ``text/plain`` content type and
        Prometheus version parameter.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
