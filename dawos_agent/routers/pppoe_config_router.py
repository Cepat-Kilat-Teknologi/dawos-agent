"""PPPoE runtime configuration API endpoints.

Provides REST endpoints for reading and updating the PPPoE scalar
settings (``service-name``, ``ac-name``, ``verbose``) in the
accel-ppp ``[pppoe]`` configuration section.

Interface bindings are managed by :mod:`~dawos_agent.routers.pppoe`,
and PADO delay by :mod:`~dawos_agent.routers.pado_router`.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    PppoeRuntimeConfigResponse,
    PppoeRuntimeConfigUpdateRequest,
)
from ..services import pppoe_config
from ..services.accel import reload_config

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pppoe/runtime", tags=["pppoe-runtime"])


@router.get("", response_model=PppoeRuntimeConfigResponse)
async def get_pppoe_runtime(_key: str = ViewerKey):
    """Read the current PPPoE runtime configuration.

    Returns the ``service-name``, ``ac-name``, and ``verbose`` settings
    from the ``[pppoe]`` section of ``accel-ppp.conf``.

    Returns:
        PppoeRuntimeConfigResponse: Current PPPoE runtime settings.

    Raises:
        HTTPException(404): If the configuration file is not found.
        HTTPException(500): If the configuration cannot be read.
    """
    try:
        data = pppoe_config.get_pppoe_runtime_config()
        return PppoeRuntimeConfigResponse(**data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Failed to read PPPoE runtime config: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("", response_model=PppoeRuntimeConfigResponse)
async def set_pppoe_runtime(
    req: PppoeRuntimeConfigUpdateRequest,
    _key: str = ApiKey,
):
    """Update PPPoE runtime configuration and reload accel-ppp.

    Only fields present in the request body are updated; omitted fields
    retain their current values.  After writing, triggers a graceful
    accel-ppp reload so the new settings take effect on new sessions.

    Args:
        req: Request body with optional ``service_name``, ``ac_name``,
            and ``verbose`` fields.

    Returns:
        PppoeRuntimeConfigResponse: Updated PPPoE runtime settings.

    Raises:
        HTTPException(400): If the request is invalid or empty.
        HTTPException(404): If the configuration file is not found.
        HTTPException(500): If the write or reload fails.
    """
    try:
        pppoe_config.set_pppoe_runtime_config(
            service_name=req.service_name,
            ac_name=req.ac_name,
            verbose=req.verbose,
        )
        try:
            await reload_config()
        except Exception as reload_exc:
            log.warning("PPPoE config saved but reload failed: %s", reload_exc)

        data = pppoe_config.get_pppoe_runtime_config()
        return PppoeRuntimeConfigResponse(**data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Failed to update PPPoE runtime config: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
