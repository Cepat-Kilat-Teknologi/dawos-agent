"""ASGI middleware for request tracing, rate limiting, and audit logging.

Each middleware is mounted in :mod:`dawos_agent.app` via ``app.add_middleware``
or manual ASGI wrapping.  They execute in reverse registration order (last
registered runs first on the request path, last on the response path).
"""

from __future__ import annotations

import contextvars
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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


class RequestIdMiddleware(BaseHTTPMiddleware):
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
