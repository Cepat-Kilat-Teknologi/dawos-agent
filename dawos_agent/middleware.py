"""ASGI middleware for request tracing, rate limiting, and audit logging.

Each middleware is mounted in :mod:`dawos_agent.app` via ``app.add_middleware``
or manual ASGI wrapping.  They execute in reverse registration order (last
registered runs first on the request path, last on the response path).
"""

from __future__ import annotations

import contextvars
import logging
import time
import uuid

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


class RequestIdMiddleware(BaseHTTPMiddleware):  # pylint: disable=too-few-public-methods
    """Attach a unique trace ID to every request/response cycle.

    Processing logic:

    1. If the caller supplies an ``X-Request-ID`` header, that value is
       reused (enables distributed tracing from an upstream gateway).
    2. Otherwise a random UUID-4 is generated.
    3. The ID is stored in :data:`request_id_var` so downstream code
       (services, logging filters) can read it without parameter passing.
    4. The same ID is echoed back in the ``X-Request-ID`` response header.
    """

    async def dispatch(self, request: Request, call_next):
        """Process the request and attach the trace ID."""
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
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
client IP, method, path, request ID, status code, and response time.
Uses the same format (text or JSON) as the application logger, but
the separate logger name allows filtering in log aggregators::

    journalctl -u dawos-agent | grep 'dawos_agent.audit'
"""


class AuditLogMiddleware(BaseHTTPMiddleware):  # pylint: disable=too-few-public-methods
    """Log all mutating HTTP requests to a dedicated audit logger.

    Only ``POST``, ``PUT``, ``PATCH``, and ``DELETE`` requests are
    recorded.  Read-only ``GET`` and ``HEAD`` requests are ignored to
    keep the audit trail focused on state-changing operations.

    Each audit log entry includes:

    * ``method`` — HTTP method
    * ``path`` — request path (no query string)
    * ``client_ip`` — remote address
    * ``request_id`` — trace ID from :data:`request_id_var`
    * ``status`` — HTTP response status code
    * ``duration_ms`` — response time in milliseconds
    """

    async def dispatch(self, request: Request, call_next):
        """Process the request and emit an audit log if mutating."""
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        audit_log.info(
            "AUDIT method=%s path=%s client_ip=%s request_id=%s"
            " status=%d duration_ms=%.1f",
            request.method,
            request.url.path,
            request.client.host if request.client else "-",
            request_id_var.get(),
            response.status_code,
            duration_ms,
        )

        return response
