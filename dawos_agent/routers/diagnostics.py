"""BNG diagnostics API endpoints.

Provides a comprehensive health-check endpoint that runs multiple
diagnostic probes against the BNG host and returns an aggregated
report covering service status, connectivity, and resource usage.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ViewerKey
from ..models.schemas import DiagnosticsResponse
from ..services import diagnostics

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/diagnostics", tags=["diagnostics"])


@router.get("/doctor", response_model=DiagnosticsResponse)
async def doctor(_key: str = ViewerKey):
    """Run all BNG health checks and return aggregated results.

    Executes a battery of diagnostic probes (service status, resource
    utilisation, connectivity checks) and returns a structured report
    with per-check pass/fail status and an overall health verdict.

    Returns:
        DiagnosticsResponse: Aggregated health-check results.

    Raises:
        HTTPException(500): If the diagnostic runner itself fails.
    """
    try:
        data = await diagnostics.run_doctor()
        return DiagnosticsResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
