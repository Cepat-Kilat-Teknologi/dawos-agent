"""Prometheus metric definitions for dawos-agent.

Centralises all :mod:`prometheus_client` metric objects so they can be
imported and updated from any module (middleware, services, retry logic)
without circular dependencies.  The ``/metrics`` endpoint exposed by
:mod:`dawos_agent.routers.metrics_router` renders these metrics in
Prometheus text exposition format.

Metric naming follows the `Prometheus naming conventions
<https://prometheus.io/docs/practices/naming/>`_:

* ``dawos_`` prefix to identify the application.
* ``_total`` suffix on Counters.
* ``_seconds`` suffix on time-based Histograms.

Labels
------
HTTP metrics use ``method`` and ``endpoint`` labels.  The ``endpoint``
label contains the **route template** (e.g. ``/api/v1/sessions/{username}``)
rather than the concrete URL, which prevents cardinality explosion from
dynamic path segments.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# HTTP request metrics (updated by MetricsMiddleware)
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL = Counter(
    "dawos_http_requests_total",
    "Total HTTP requests received by the agent.",
    ["method", "endpoint", "status"],
)
"""Counter incremented on every HTTP response.

Labels:
    method: HTTP method (GET, POST, PUT, DELETE, ...).
    endpoint: Route path template (e.g. ``/api/v1/sessions``).
    status: HTTP response status code as a string (e.g. ``"200"``).
"""

HTTP_REQUEST_DURATION = Histogram(
    "dawos_http_request_duration_seconds",
    "HTTP request processing time in seconds.",
    ["method", "endpoint"],
)
"""Histogram recording response latency per route.

Labels:
    method: HTTP method.
    endpoint: Route path template.
"""

# ---------------------------------------------------------------------------
# accel-cmd metrics (updated by services/accel.py and retry.py)
# ---------------------------------------------------------------------------

ACCEL_CMD_ERRORS_TOTAL = Counter(
    "dawos_accel_cmd_errors_total",
    "Total accel-cmd command failures (non-zero exit code).",
)
"""Counter incremented when ``accel-cmd`` exits with a non-zero code."""

ACCEL_CMD_RETRIES_TOTAL = Counter(
    "dawos_accel_cmd_retries_total",
    "Total retry attempts for transient accel-cmd failures.",
)
"""Counter incremented on each retry attempt (not the initial try)."""

# ---------------------------------------------------------------------------
# Rate limiting metrics (updated by MetricsMiddleware)
# ---------------------------------------------------------------------------

RATE_LIMIT_HITS_TOTAL = Counter(
    "dawos_rate_limit_hits_total",
    "Total requests rejected by the rate limiter (HTTP 429).",
)
"""Counter incremented when a request is rejected with HTTP 429."""
