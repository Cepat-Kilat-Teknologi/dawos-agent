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

from . import __version__
from .config import settings
from .routers import (
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
    monitoring_router,
    network,
    ntp,
    pado_router,
    pppoe,
    routing,
    scheduler,
    service,
    session_control,
    sessions,
    system,
    traffic,
    vrrp_router,
    zone_router,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,  # noqa: ARG001  # pylint: disable=redefined-outer-name,unused-argument
):
    """Manage application startup and shutdown lifecycle events.

    On startup, logs the agent version, listening port, and node name to
    aid operational debugging.  On shutdown, emits a clean log line so
    log aggregators can distinguish graceful stops from crashes.
    """
    import logging  # pylint: disable=import-outside-toplevel

    log = logging.getLogger("dawos_agent")
    log.info(
        "dawos-agent %s starting on %s (node=%s)",
        __version__,
        settings.port,
        settings.node_name,
    )
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

# Public (no auth) ----------------------------------------------------------
app.include_router(health.router)

# Protected (require API key) -----------------------------------------------
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
app.include_router(diagnostics.router)
app.include_router(logs.router)
