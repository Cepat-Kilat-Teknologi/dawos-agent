"""FastAPI application factory and router registration.

Assembles the dawos-agent REST API by mounting all feature routers onto a
single :class:`~fastapi.FastAPI` instance.  The module-level ``app`` object
is the ASGI application used by both the development server
(:mod:`dawos_agent.__main__`) and production deployments (e.g. Gunicorn with
Uvicorn workers).

Router layout
-------------
* **Public** — ``/health`` is unauthenticated so load-balancers and
  orchestrators can probe liveness without an API key.
* **Protected** — every other router requires a valid ``X-API-Key`` header
  (enforced per-router via the :data:`dawos_agent.auth.ApiKey` dependency).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from . import __version__
from .config import check_config, settings
from .logging import setup_logging
from .middleware import (
    AuditLogMiddleware,
    MetricsMiddleware,
    RequestIdMiddleware,
    limiter,
)
from .routers import (
    audit_router,
    bulk_router,
    checkpoint,
    config_router,
    conntrack_router,
    csv_export_router,
    dhcp_router,
    diagnostics,
    dns_forwarding,
    event_router,
    firewall,
    flow_router,
    fw_groups_router,
    health,
    ip_pool_router,
    limits_router,
    lldp_router,
    logs,
    metrics_router,
    monitoring_router,
    network,
    ntp,
    pado_router,
    playbooks_router,
    pppoe,
    pppoe_config_router,
    radius,
    routing,
    scheduler,
    service,
    session_control,
    session_history_router,
    sessions,
    system,
    traffic,
    vrrp_router,
    ws,
    zone_router,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,  # noqa: ARG001  # pylint: disable=redefined-outer-name,unused-argument
):
    """Manage application startup and shutdown lifecycle events.

    On startup, configures structured logging and logs the agent version,
    listening port, and node name to aid operational debugging.  On
    shutdown, emits a clean log line so log aggregators can distinguish
    graceful stops from crashes.
    """
    setup_logging(level=settings.log_level, fmt=settings.log_format)
    log.info(
        "dawos-agent %s starting on %s (node=%s)",
        __version__,
        settings.port,
        settings.node_name,
    )
    check_config(logger=log)
    yield
    log.info("dawos-agent shutting down")


log = logging.getLogger("dawos_agent")


async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return a sanitized 500 for any exception not handled by a route.

    Prevents raw command output, stack traces, or file paths from reaching
    clients: the real error is logged server-side, keyed by request ID,
    while the response body carries only ``{"error", "request_id"}``
    (DA-M03).
    """
    rid = getattr(request.state, "request_id", "") or request.headers.get(
        "x-request-id", ""
    )
    log.error("Unhandled exception [%s]: %s", rid, exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal", "request_id": rid},
    )


app = FastAPI(
    title="dawos-agent",
    description="PPP router management agent",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware (executes in reverse order — last added runs first) -------------
app.add_middleware(MetricsMiddleware)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(RequestIdMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Catch-all so uncaught exceptions never leak internal detail (DA-M03).
app.add_exception_handler(Exception, _unhandled_exception_handler)
# Added last so it runs first on the request path: reject over-limit
# callers before any downstream work. Inert when DAWOS_RATE_LIMIT is empty.
app.add_middleware(SlowAPIMiddleware)

# Public (no auth) ----------------------------------------------------------
app.include_router(health.router)
app.include_router(metrics_router.router)

# Protected (require API key) -----------------------------------------------
app.include_router(audit_router.router)
app.include_router(bulk_router.router)
app.include_router(system.router)
app.include_router(service.router)
app.include_router(sessions.router)
app.include_router(config_router.router)
app.include_router(network.router)
app.include_router(firewall.router)
app.include_router(pppoe.router)
app.include_router(radius.router)
app.include_router(traffic.router)
app.include_router(routing.router)
app.include_router(checkpoint.router)
app.include_router(conntrack_router.router)
app.include_router(scheduler.router)
app.include_router(dns_forwarding.router)
app.include_router(ntp.router)
app.include_router(session_control.router)
app.include_router(limits_router.router)
app.include_router(pado_router.router)
app.include_router(pppoe_config_router.router)
app.include_router(ip_pool_router.router)
app.include_router(session_history_router.router)
app.include_router(lldp_router.router)
app.include_router(dhcp_router.router)
app.include_router(flow_router.router)
app.include_router(event_router.router)
app.include_router(zone_router.router)
app.include_router(fw_groups_router.router)
app.include_router(vrrp_router.router)
app.include_router(monitoring_router.router)
app.include_router(playbooks_router.router)
app.include_router(diagnostics.router)
app.include_router(logs.router)
app.include_router(csv_export_router.router)

# WebSocket (authenticated via query parameter) ----------------------------
app.include_router(ws.router)
