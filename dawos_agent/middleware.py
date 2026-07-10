"""ASGI middleware for request tracing, rate limiting, metrics, and audit logging.

Each middleware is mounted in :mod:`dawos_agent.app` via ``app.add_middleware``
or manual ASGI wrapping.  They execute in reverse registration order (last
registered runs first on the request path, last on the response path).
"""

from __future__ import annotations

import collections
import contextvars
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .config import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request ID
# ---------------------------------------------------------------------------

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)
"""Context variable holding the current request's trace ID.

Accessible from any coroutine running inside a request lifecycle via::

    from dawos_agent.middleware import request_id_var
    rid = request_id_var.get()
"""

#: Validate caller-supplied request IDs: printable ASCII, 1–128 chars,
#: no control characters or whitespace beyond plain space.  Rejects
#: oversized or malformed values that could pollute logs (DA-M05).
_RE_VALID_REQUEST_ID = re.compile(r"^[\x20-\x7E]{1,128}$")


class RequestIdMiddleware(BaseHTTPMiddleware):  # pylint: disable=too-few-public-methods
    """Attach a unique trace ID to every request/response cycle.

    Processing logic:

    1. If the caller supplies an ``X-Request-ID`` header **and** it
       passes format validation (printable ASCII, ≤128 chars), that
       value is reused (enables distributed tracing from an upstream
       gateway).
    2. Otherwise a random UUID-4 is generated.
    3. The ID is stored in :data:`request_id_var` so downstream code
       (services, logging filters) can read it without parameter passing.
    4. The same ID is echoed back in the ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next):
        """Process the request and attach the trace ID."""
        supplied = request.headers.get("x-request-id", "")
        rid = (
            supplied
            if supplied and _RE_VALID_REQUEST_ID.match(supplied)
            else uuid.uuid4().hex
        )
        request_id_var.set(rid)
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

_default_limits = [settings.rate_limit] if settings.rate_limit else []

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=_default_limits,
)
"""Global rate limiter instance.

Applies ``DAWOS_RATE_LIMIT`` (default ``120/minute``) per remote IP
to every endpoint except those explicitly exempted.  Health endpoints
are exempted by marking them with ``@limiter.exempt``.
"""

# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

audit_log = logging.getLogger("dawos_agent.audit")
"""Dedicated logger for write-operation audit trail.

Logs every mutating HTTP request (POST, PUT, PATCH, DELETE) with
client IP, method, path, request ID, role, status code, and response
time.  Uses the same format (text or JSON) as the application logger,
but the separate logger name allows filtering in log aggregators::

    journalctl -u dawos-agent | grep 'dawos_agent.audit'
"""

#: In-memory ring buffer that stores the most recent audit entries.
#: The buffer size is controlled by ``DAWOS_AUDIT_BUFFER_SIZE`` (default
#: 1000).  Entries are plain dicts matching the :class:`AuditEntry`
#: Pydantic model schema.  Access the buffer from routers via::
#:
#:     from dawos_agent.middleware import audit_buffer
#:     entries = list(audit_buffer)
audit_buffer: collections.deque[dict] = collections.deque(
    maxlen=settings.audit_buffer_size,
)


class AuditLogMiddleware(BaseHTTPMiddleware):  # pylint: disable=too-few-public-methods
    """Log all mutating HTTP requests to a dedicated audit logger.

    Only ``POST``, ``PUT``, ``PATCH``, and ``DELETE`` requests are
    recorded.  Read-only ``GET`` and ``HEAD`` requests are ignored to
    keep the audit trail focused on state-changing operations.

    Each audit log entry includes:

    * ``method`` -- HTTP method
    * ``path`` -- request path (no query string)
    * ``client_ip`` -- remote address
    * ``request_id`` -- trace ID from :data:`request_id_var`
    * ``role`` -- RBAC role of the caller (``viewer``, ``operator``,
      ``admin``) or ``-`` if authentication was bypassed or failed
    * ``status`` -- HTTP response status code
    * ``duration_ms`` -- response time in milliseconds

    In addition to logging, every entry is appended to
    :data:`audit_buffer` — an in-memory ring buffer exposed via the
    ``GET /api/v1/audit`` admin endpoint.
    """

    async def dispatch(self, request: Request, call_next):
        """Process the request and emit an audit log if mutating."""
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        # Read the role stored by the RBAC auth dependency.  Falls back
        # to "-" when the endpoint is unauthenticated or auth failed
        # before the role could be stored on request state.
        role = getattr(request.state, "role", "-")
        client_ip = request.client.host if request.client else "-"
        rid = request_id_var.get()

        audit_log.info(
            "AUDIT method=%s path=%s client_ip=%s request_id=%s"
            " role=%s status=%d duration_ms=%.1f",
            request.method,
            request.url.path,
            client_ip,
            rid,
            role,
            response.status_code,
            duration_ms,
        )

        # Append to the in-memory ring buffer for the audit API.
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": request.method,
            "path": request.url.path,
            "client_ip": client_ip,
            "request_id": rid,
            "role": role,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }
        audit_buffer.append(entry)

        # Fire webhook notification (non-blocking).
        from .webhooks import fire_webhook  # pylint: disable=import-outside-toplevel

        fire_webhook(
            {
                "event": "api.request",
                **entry,
            }
        )

        return response


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

# Paths excluded from metrics recording to avoid self-instrumentation
# and noise from high-frequency health probes.
_METRICS_SKIP_PATHS = frozenset({"/metrics", "/health", "/health/ready"})


class MetricsMiddleware:
    """Record HTTP request metrics for Prometheus exposition.

    Implemented as a **pure ASGI middleware** (not
    :class:`~starlette.middleware.base.BaseHTTPMiddleware`) to avoid
    known issues with stacking three or more ``BaseHTTPMiddleware``
    layers in Starlette.

    Instruments every request with:

    * ``dawos_http_requests_total`` -- counter with method, endpoint
      (route template), and status labels.
    * ``dawos_http_request_duration_seconds`` -- histogram with method
      and endpoint labels.
    * ``dawos_rate_limit_hits_total`` -- counter incremented when the
      response status is 429 (rate limit exceeded).

    The ``/metrics``, ``/health``, and ``/health/ready`` paths are
    excluded to avoid self-instrumentation loops and noisy probe
    traffic in the metric series.

    The ``endpoint`` label uses the **route path template** (e.g.
    ``/api/v1/sessions/{username}``) rather than the concrete URL to
    prevent label cardinality explosion from dynamic path segments.
    """

    def __init__(self, app):  # noqa: D107
        self.app = app

    async def __call__(self, scope, receive, send):
        """Process the ASGI request and record Prometheus metrics."""
        if scope["type"] != "http" or scope["path"] in _METRICS_SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        # Lazy import to avoid circular dependency at module load time.
        from .metrics import (  # pylint: disable=import-outside-toplevel
            HTTP_REQUEST_DURATION,
            HTTP_REQUESTS_TOTAL,
            RATE_LIMIT_HITS_TOTAL,
        )

        method = scope["method"]
        status_code = 500  # default if response never starts

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        start = time.monotonic()
        await self.app(scope, receive, send_wrapper)
        duration = time.monotonic() - start

        # Prefer the route template to avoid cardinality explosion.
        route = scope.get("route")
        endpoint = getattr(route, "path", scope["path"]) if route else scope["path"]

        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status=str(status_code),
        ).inc()
        HTTP_REQUEST_DURATION.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)

        if status_code == 429:
            RATE_LIMIT_HITS_TOTAL.inc()
