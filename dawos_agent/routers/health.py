"""Health check API endpoints.

Provides public (no authentication required) probes used by load balancers,
the dawu-radius node-discovery system, and container orchestrators.

* ``GET /health`` — **liveness** probe: always returns 200 if the process
  is running.
* ``GET /health/ready`` — **readiness** probe: returns 200 only when the
  agent can communicate with the accel-ppp daemon, 503 otherwise.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import __version__
from ..config import settings
from ..middleware import limiter
from ..models.schemas import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])

log = logging.getLogger(__name__)

_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
@limiter.exempt
async def health():
    """Perform a basic health check.

    Always returns HTTP 200 with the node name, agent version, and
    process uptime in seconds.  No authentication is required so that
    external probes can reach this endpoint without credentials.

    Returns:
        HealthResponse: Status ``ok``, node name, version, and uptime.
    """
    return HealthResponse(
        status="ok",
        node_name=settings.node_name,
        version=__version__,
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
@limiter.exempt
async def readiness():
    """Check whether the agent is ready to serve requests.

    Verifies that the accel-ppp CLI daemon is reachable by running
    ``accel-cmd show version``.  Returns HTTP 200 when all checks pass,
    HTTP 503 when any dependency is unreachable.

    Returns:
        ReadinessResponse: Readiness status with per-check details.
    """
    checks: list[dict] = []

    # Check accel-ppp daemon
    accel_ok = False
    detail = ""
    try:
        proc = await asyncio.create_subprocess_exec(
            settings.accel_cmd,
            "-H",
            f"127.0.0.1:{settings.accel_cli_port}",
            "show",
            "version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        accel_ok = proc.returncode == 0
        detail = stdout.decode().strip() if accel_ok else "accel-ppp unreachable"
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as exc:
        detail = str(exc)

    checks.append({"service": "accel-ppp", "reachable": accel_ok, "detail": detail})

    ready = all(c["reachable"] for c in checks)
    body = ReadinessResponse(ready=ready, checks=checks)

    if not ready:
        return JSONResponse(status_code=503, content=body.model_dump())
    return body
