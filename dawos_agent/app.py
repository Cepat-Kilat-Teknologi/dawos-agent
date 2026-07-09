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

from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

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
    routing,
    scheduler,
    service,
    session_control,
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

    import logging  # pylint: disable=import-outside-toplevel

    log = logging.getLogger("dawos_agent")
    log.info(
        "dawos-agent %s starting on %s (node=%s)",
        __version__,
        settings.port,
        settings.node_name,
    )
    check_config(logger=log)
    yield
    log.info("dawos-agent shutting down")


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
app.include_router(ip_pool_router.router)
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

# WebSocket (authenticated via query parameter) ----------------------------
app.include_router(ws.router)
