"""Monitoring and metrics export API endpoints.

Provides REST endpoints for managing Prometheus and SNMP monitoring
exporters on the BNG host.  Supports status checks, metrics retrieval,
exporter enable/disable, and service restarts.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    ConfigureExporterRequest,
    ExporterActionResponse,
    ExporterMetricsResponse,
    ExporterRestartResponse,
    MonitoringStatusResponse,
)
from ..services import monitoring

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


@router.get("/status", response_model=MonitoringStatusResponse)
async def monitoring_status(_key: str = ViewerKey):
    """Retrieve the monitoring stack status.

    Returns the operational state of all configured monitoring
    exporters (Prometheus node exporter, SNMP exporter, etc.).

    Returns:
        MonitoringStatusResponse: Per-exporter status summary.

    Raises:
        HTTPException(500): If the status check fails.
    """
    try:
        data = await monitoring.monitoring_status()
        return MonitoringStatusResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/metrics/{service}", response_model=ExporterMetricsResponse)
async def exporter_metrics(service: str, _key: str = ViewerKey):
    """Get metrics from a specific monitoring exporter.

    Scrapes the named exporter's metrics endpoint and returns the
    raw Prometheus-format metrics text.

    Args:
        service: The exporter service name to query.

    Returns:
        ExporterMetricsResponse: Raw metrics output from the exporter.

    Raises:
        HTTPException(500): If the metrics cannot be scraped.
    """
    try:
        data = await monitoring.exporter_metrics(service)
        return ExporterMetricsResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/configure", response_model=ExporterActionResponse)
async def configure_exporter(req: ConfigureExporterRequest, _key: str = ApiKey):
    """Enable or disable a monitoring exporter service.

    Starts or stops the named exporter and optionally enables or
    disables it for automatic startup on boot.

    Args:
        req: Request body with service name and enable flag.

    Returns:
        ExporterActionResponse: Success status and result message.

    Raises:
        HTTPException(500): If the configuration change fails.
    """
    try:
        data = await monitoring.configure_exporter(req.service, enable=req.enable)
        return ExporterActionResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/restart/{service}", response_model=ExporterRestartResponse)
async def exporter_restart(service: str, _key: str = ApiKey):
    """Restart a monitoring exporter service.

    Issues a ``systemctl restart`` for the named exporter and returns
    the operation result.

    Args:
        service: The exporter service name to restart.

    Returns:
        ExporterRestartResponse: Success status and result message.

    Raises:
        HTTPException(500): If the restart operation fails.
    """
    try:
        data = await monitoring.exporter_restart(service)
        return ExporterRestartResponse(**data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
