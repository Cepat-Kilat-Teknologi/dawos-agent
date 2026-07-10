"""Network management API endpoints.

Provides REST endpoints for managing network interfaces, VLAN
sub-interfaces, static routes, and DNS resolver configuration on the
BNG host.  Uses ``ip`` commands for interface and route operations and
``/etc/resolv.conf`` for DNS management.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path

from ..auth import ApiKey, ViewerKey
from ..constants import RE_SAFE_IFACE
from ..models.schemas import (
    DnsConfig,
    DnsResponse,
    DnsUpdateRequest,
    InterfaceConfigRequest,
    InterfaceConfigResponse,
    InterfaceDetail,
    InterfaceListResponse,
    RouteAddRequest,
    RouteDeleteRequest,
    RouteListResponse,
    RouteResponse,
    VlanCreateRequest,
    VlanDeleteResponse,
    VlanListResponse,
    VlanStateRequest,
    VlanStateResponse,
)
from ..services import network

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/network", tags=["network"])


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


@router.get("/interfaces", response_model=InterfaceListResponse)
async def list_interfaces(_key: str = ViewerKey):
    """List all network interfaces with addresses and operational state.

    Runs ``ip -j addr show`` and returns a structured list of every
    interface including its name, MAC address, IP addresses, MTU, and
    link state.

    Returns:
        InterfaceListResponse: Count and list of interface records.

    Raises:
        HTTPException(500): If the interface enumeration fails.
    """
    try:
        interfaces = await network.list_interfaces()
        return InterfaceListResponse(count=len(interfaces), interfaces=interfaces)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/interfaces/{name}", response_model=InterfaceDetail)
async def get_interface(name: str, _key: str = ViewerKey):
    """Get detailed information for a specific network interface.

    Returns full interface details including all assigned addresses,
    statistics counters, and driver information.

    Args:
        name: The interface name to query (e.g. ``eth0``).

    Returns:
        InterfaceDetail: Comprehensive interface information.

    Raises:
        HTTPException(404): If the interface does not exist.
    """
    try:
        return await network.get_interface(name)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/interfaces/{name}", response_model=InterfaceConfigResponse)
async def configure_interface(
    req: InterfaceConfigRequest,
    name: str = Path(pattern=RE_SAFE_IFACE),
    _key: str = ApiKey,
):
    """Configure a network interface.

    Supports adding/removing IP addresses, changing the MTU, and
    setting the link state (up/down) on the named interface.

    Args:
        name: The interface name to configure.
        req: Request body with address, MTU, and/or state changes.

    Returns:
        InterfaceConfigResponse: Success status and confirmation message.

    Raises:
        HTTPException(400): If the configuration parameters are invalid.
    """
    try:
        msg = await network.configure_interface(
            name,
            address=req.address,
            remove_address=req.remove_address,
            mtu=req.mtu,
            state=req.state,
        )
        return InterfaceConfigResponse(success=True, message=msg, interface=name)
    except RuntimeError as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(
            status_code=400, detail="Interface configuration failed"
        ) from exc


# ---------------------------------------------------------------------------
# VLANs
# ---------------------------------------------------------------------------


@router.post("/vlans", response_model=VlanDeleteResponse)
async def create_vlan(req: VlanCreateRequest, _key: str = ApiKey):
    """Create a VLAN sub-interface.

    Creates an 802.1Q VLAN interface on the specified parent interface
    and optionally assigns an IP address.

    Args:
        req: Request body with parent interface, VLAN ID, and address.

    Returns:
        VlanDeleteResponse: Success status and created VLAN name.

    Raises:
        HTTPException(400): If the VLAN cannot be created.
    """
    try:
        vlan_name = await network.create_vlan(
            parent=req.parent,
            vlan_id=req.vlan_id,
            address=req.address,
        )
        return VlanDeleteResponse(
            success=True,
            message=f"VLAN {req.vlan_id} created on {req.parent}",
            name=vlan_name,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/vlans/{name}", status_code=204)
async def delete_vlan(name: str = Path(pattern=RE_SAFE_IFACE), _key: str = ApiKey):
    """Delete a VLAN sub-interface.

    Removes the named VLAN interface from the system.

    Args:
        name: The VLAN interface name to delete (e.g. ``eth0.100``).

    Raises:
        HTTPException(404): If the VLAN does not exist.
        HTTPException(500): If the delete otherwise fails.
    """
    try:
        await network.delete_vlan(name)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if (
            "cannot find" in msg
            or "no such" in msg
            or "does not exist" in msg
            or "not found" in msg
        ):
            raise HTTPException(
                status_code=404, detail=f"VLAN '{name}' not found"
            ) from exc
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/vlans", response_model=VlanListResponse)
async def list_vlans(_key: str = ViewerKey):
    """Auto-detect all VLANs on the system.

    Uses kernel-level VLAN metadata (``ip -j -d link show type vlan``)
    to return parent interface, VLAN ID, and 802.1Q protocol info.
    """
    try:
        vlans = await network.list_vlans()
        return VlanListResponse(count=len(vlans), vlans=vlans)
    except RuntimeError as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("/vlans/{name}", response_model=VlanStateResponse)
async def set_vlan_state(
    req: VlanStateRequest,
    name: str = Path(pattern=RE_SAFE_IFACE),
    _key: str = ApiKey,
):
    """Enable or disable a VLAN interface (bring up/down)."""
    try:
        msg = await network.set_vlan_state(name, req.state)
        return VlanStateResponse(
            success=True,
            message=msg,
            name=name,
            state=req.state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/routes", response_model=RouteListResponse)
async def list_routes(_key: str = ViewerKey):
    """Show the IPv4 routing table.

    Returns all IPv4 routes from the main routing table via
    ``ip -j route show``.

    Returns:
        RouteListResponse: Count and list of route entries.

    Raises:
        HTTPException(500): If the routing table cannot be read.
    """
    try:
        routes = await network.list_routes()
        return RouteListResponse(count=len(routes), routes=routes)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/routes", response_model=RouteResponse)
async def add_route(req: RouteAddRequest, _key: str = ApiKey):
    """Add a static route to the routing table.

    Creates a route to the specified destination via the given gateway
    and/or device, with an optional metric.

    Args:
        req: Request body with destination, gateway, device, and metric.

    Returns:
        RouteResponse: Success status and confirmation message.

    Raises:
        HTTPException(400): If the route parameters are invalid.
    """
    try:
        msg = await network.add_route(
            destination=req.destination,
            gateway=req.gateway,
            device=req.device,
            metric=req.metric,
        )
        return RouteResponse(success=True, message=msg)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/routes", status_code=204)
async def delete_route(req: RouteDeleteRequest, _key: str = ApiKey):
    """Delete a route from the routing table.

    Removes the route matching the specified destination and optional
    gateway.

    Args:
        req: Request body with destination and optional gateway.

    Raises:
        HTTPException(400): If the route cannot be deleted.
    """
    try:
        await network.delete_route(
            destination=req.destination,
            gateway=req.gateway,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# DNS
# ---------------------------------------------------------------------------


@router.get("/dns", response_model=DnsResponse)
async def get_dns(_key: str = ViewerKey):
    """Show current DNS configuration from ``/etc/resolv.conf``.

    Parses the resolver configuration file and returns the list of
    nameservers and search domains.

    Returns:
        DnsResponse: Current nameservers and search domains.

    Raises:
        HTTPException(500): If the DNS configuration cannot be read.
    """
    try:
        config = network.get_dns()
        return DnsResponse(success=True, message="OK", config=config)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("/dns", response_model=DnsResponse)
async def set_dns(req: DnsUpdateRequest, _key: str = ApiKey):
    """Update DNS configuration in ``/etc/resolv.conf``.

    Overwrites the resolver configuration with the provided nameservers
    and search domains.

    Args:
        req: Request body with nameserver list and search domain list.

    Returns:
        DnsResponse: Updated DNS configuration.

    Raises:
        HTTPException(500): If the configuration file cannot be written.
    """
    try:
        network.set_dns(
            nameservers=req.nameservers,
            search_domains=req.search_domains,
        )
        config = DnsConfig(
            nameservers=req.nameservers,
            search_domains=req.search_domains,
        )
        return DnsResponse(success=True, message="DNS updated", config=config)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
