"""PADO delay management API endpoints.

Provides REST endpoints for reading and setting the PPPoE Active
Discovery Offer (PADO) delay in the accel-ppp configuration.  PADO
delay controls how long the BNG waits before responding to PADI
requests, useful for load distribution across multiple BNG nodes.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import PadoDelayResponse, SetPadoDelayRequest
from ..services import pado_delay
from ..services.accel import reload_config

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pppoe/pado", tags=["pado-delay"])


@router.get("", response_model=PadoDelayResponse)
async def get_pado_delay(_key: str = ViewerKey):
    """Read the current PADO delay configuration.

    Returns the delay value (in milliseconds) and the minimum session
    threshold from the accel-ppp ``[pppoe]`` config section.

    Returns:
        PadoDelayResponse: Current delay and min_sessions values.

    Raises:
        HTTPException(404): If the configuration file is not found.
        HTTPException(500): If the configuration cannot be read.
    """
    try:
        data = pado_delay.get_pado_delay()
        return PadoDelayResponse(**data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("", response_model=PadoDelayResponse)
async def set_pado_delay(req: SetPadoDelayRequest, _key: str = ApiKey):
    """Set the PADO delay and reload accel-ppp.

    Updates the PADO delay and minimum session threshold in the config
    file, then triggers a graceful accel-ppp reload.

    Args:
        req: Request body with delay (ms) and min_sessions values.

    Returns:
        PadoDelayResponse: Updated PADO delay configuration.

    Raises:
        HTTPException(400): If the delay or threshold values are invalid.
        HTTPException(404): If the configuration file is not found.
        HTTPException(500): If the write or reload fails.
    """
    try:
        pado_delay.set_pado_delay(
            delay=req.delay,
            min_sessions=req.min_sessions,
        )
        try:
            await reload_config()
        except Exception as reload_exc:
            log.warning("PADO delay saved but reload failed: %s", reload_exc)

        data = pado_delay.get_pado_delay()
        return PadoDelayResponse(**data)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
