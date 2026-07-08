"""PPPoE interface binding endpoints.

Manage which interfaces accel-ppp listens on for PPPoE sessions by
editing the ``[pppoe]`` section of ``/etc/accel-ppp.conf``.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey
from ..models.schemas import (
    MacFilterListResponse,
    MacFilterRequest,
    MacFilterResponse,
    PppoeAddRequest,
    PppoeInterfaceListResponse,
    PppoeResponse,
)
from ..services import pppoe
from ..services.accel import mac_filter, reload_config

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pppoe", tags=["pppoe"])


# ---------------------------------------------------------------------------
# PPPoE interface management
# ---------------------------------------------------------------------------


@router.get("/interfaces", response_model=PppoeInterfaceListResponse)
async def list_pppoe_interfaces(_key: str = ApiKey):
    """List PPPoE listener interfaces from the accel-ppp config.

    Parses the ``[pppoe]`` section of ``/etc/accel-ppp.conf`` and
    returns each interface entry with its options.

    Returns:
        PppoeInterfaceListResponse: Count and list of listener entries.

    Raises:
        HTTPException(404): If the configuration file is not found.
        HTTPException(500): If the configuration cannot be parsed.
    """
    try:
        interfaces = pppoe.list_pppoe_interfaces()
        return PppoeInterfaceListResponse(
            count=len(interfaces),
            interfaces=interfaces,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/interfaces", response_model=PppoeResponse)
async def add_pppoe_interface(req: PppoeAddRequest, _key: str = ApiKey):
    """Add a PPPoE listener interface and reload accel-ppp.

    Appends the interface to the ``[pppoe]`` section of the config file.
    After modification, accel-ppp is reloaded to apply the change.

    Args:
        req: Request body with interface name and optional per-interface
            options.

    Returns:
        PppoeResponse: Success status and confirmation message.

    Raises:
        HTTPException(404): If the configuration file is not found.
        HTTPException(409): If the interface is already configured.
        HTTPException(500): If the write or reload fails.
    """
    try:
        msg = pppoe.add_pppoe_interface(
            interface=req.interface,
            options=req.options,
        )
        # Reload accel-ppp so it starts listening on the new interface
        try:
            await reload_config()
        except Exception as reload_exc:
            log.warning("Config saved but reload failed: %s", reload_exc)
            msg += " (reload failed — manual restart may be needed)"

        return PppoeResponse(success=True, message=msg)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/interfaces/{name}", status_code=204)
async def remove_pppoe_interface(name: str, _key: str = ApiKey):
    """Remove a PPPoE listener interface and reload accel-ppp.

    Deletes the named interface from the ``[pppoe]`` config section
    and triggers a graceful accel-ppp reload.

    Args:
        name: The interface name to remove (e.g. ``eth1``).

    Raises:
        HTTPException(404): If the config file or interface is not found.
        HTTPException(500): If the write or reload fails.
    """
    try:
        pppoe.remove_pppoe_interface(interface=name)
        try:
            await reload_config()
        except Exception as reload_exc:
            log.warning("Config saved but reload failed: %s", reload_exc)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# MAC filter
# ---------------------------------------------------------------------------


@router.get("/mac-filter", response_model=MacFilterListResponse)
async def list_mac_filter(_key: str = ApiKey):
    """List the PPPoE MAC address filter entries.

    Runs ``accel-cmd pppoe mac-filter show`` and returns the raw
    output along with the count of filter entries.

    Returns:
        MacFilterListResponse: Raw output and entry count.

    Raises:
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        raw = await mac_filter("show")
        count = len([ln for ln in raw.splitlines() if ln.strip() and ":" in ln])
        return MacFilterListResponse(raw_output=raw, count=count)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/mac-filter", response_model=MacFilterResponse)
async def add_mac(req: MacFilterRequest, _key: str = ApiKey):
    """Add a MAC address to the PPPoE filter.

    Runs ``accel-cmd pppoe mac-filter add`` for the given MAC.

    Args:
        req: Request body with the MAC address to add.

    Returns:
        MacFilterResponse: Success status and confirmation message.

    Raises:
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        await mac_filter("add", req.mac)
        return MacFilterResponse(
            success=True,
            message=f"Added {req.mac}",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/mac-filter/{mac}", status_code=204)
async def delete_mac(mac: str, _key: str = ApiKey):
    """Remove a MAC address from the PPPoE filter.

    Runs ``accel-cmd pppoe mac-filter del`` for the given MAC.

    Args:
        mac: The MAC address to remove (path parameter).

    Raises:
        HTTPException(500): If the accel-cmd command fails.
    """
    try:
        await mac_filter("del", mac)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
