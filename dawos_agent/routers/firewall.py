"""Firewall, NAT, and network security management API endpoints.

Provides REST endpoints for managing the nftables firewall, NAT
masquerade, per-subscriber egress NAT mappings, IP forwarding sysctl
settings, conntrack tuning, and SNMP daemon status on the BNG host.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Path

from ..auth import ApiKey, ViewerKey
from ..constants import RE_SAFE_IP
from ..models.schemas import (
    BoxEgressRequest,
    BoxEgressResponse,
    ConntrackResponse,
    ConntrackUpdateRequest,
    FirewallRulesetResponse,
    FirewallStatus,
    NatEgressMapResponse,
    NatEgressResponse,
    NatEgressSetRequest,
    NatMasqueradeRequest,
    NatMasqueradeResponse,
    NatPublicIpRequest,
    NatStatusResponse,
    NftValidateResponse,
    SnmpStatusResponse,
    SysctlResponse,
    SysctlUpdateRequest,
)
from ..services import diagnostics, firewall, nat

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/firewall", tags=["firewall"])


# ---------------------------------------------------------------------------
# Firewall status
# ---------------------------------------------------------------------------


@router.get("/status", response_model=FirewallStatus)
async def firewall_status(_key: str = ViewerKey):
    """Check the overall firewall status.

    Returns whether nftables is active, whether NAT masquerade is
    enabled, and the current IP forwarding sysctl values.

    Returns:
        FirewallStatus: Composite firewall and NAT state.

    Raises:
        HTTPException(500): If the status check fails.
    """
    try:
        return await firewall.get_firewall_status()
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/rules", response_model=FirewallRulesetResponse)
async def list_rules(_key: str = ViewerKey):
    """List the full nftables ruleset.

    Runs ``nft list ruleset`` and returns the raw output along with
    a count of individual rules found.

    Returns:
        FirewallRulesetResponse: Raw ruleset text and rule count.

    Raises:
        HTTPException(500): If the nft command fails.
    """
    try:
        raw, count = await firewall.list_ruleset()
        return FirewallRulesetResponse(raw_output=raw, rules_count=count)
    except RuntimeError as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# ---------------------------------------------------------------------------
# NAT masquerade
# ---------------------------------------------------------------------------


@router.post("/nat/masquerade", response_model=NatMasqueradeResponse)
async def enable_masquerade(req: NatMasqueradeRequest, _key: str = ApiKey):
    """Enable NAT masquerade on a WAN interface.

    Creates a dawos-nat nftables table with postrouting masquerade.
    Idempotent — safe to call repeatedly.
    """
    try:
        msg = await firewall.setup_masquerade(req.wan_interface)
        return NatMasqueradeResponse(
            success=True,
            message=msg,
            wan_interface=req.wan_interface,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/nat/masquerade", status_code=204)
async def disable_masquerade(_key: str = ApiKey):
    """Remove the NAT masquerade table and rule.

    Deletes the ``dawos-nat`` nftables table, disabling outbound NAT.

    Raises:
        HTTPException(400): If the table cannot be removed.
    """
    try:
        await firewall.remove_masquerade()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/save", response_model=dict)
async def save_rules(_key: str = ApiKey):
    """Persist the current nftables ruleset to disk.

    Writes the live ruleset to ``/etc/nftables.conf`` so it survives
    reboots.

    Returns:
        dict: Success flag and confirmation message.

    Raises:
        HTTPException(500): If the save operation fails.
    """
    try:
        msg = await firewall.save_ruleset()
        return {"success": True, "message": msg}
    except RuntimeError as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# ---------------------------------------------------------------------------
# nft dry-run validation
# ---------------------------------------------------------------------------


@router.post("/validate", response_model=NftValidateResponse)
async def validate_ruleset(
    req: dict,
    _key: str = ApiKey,
):
    """Dry-run validate an nftables ruleset without applying it.

    Accepts ``{"ruleset": "<nft rules text>"}`` and runs ``nft -c -f``
    to catch syntax errors before they hit the live firewall.
    """
    ruleset = req.get("ruleset", "")
    if not ruleset:
        raise HTTPException(status_code=400, detail="Missing 'ruleset' field")
    try:
        result = await firewall.validate_ruleset(ruleset)
        return NftValidateResponse(**result)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# ---------------------------------------------------------------------------
# sysctl — IP forwarding
# ---------------------------------------------------------------------------


@router.get("/sysctl", response_model=SysctlResponse)
async def get_sysctl(_key: str = ViewerKey):
    """Read current IP forwarding sysctl values.

    Returns the state of ``net.ipv4.ip_forward`` and
    ``net.ipv6.conf.all.forwarding``.

    Returns:
        SysctlResponse: Current IPv4 and IPv6 forwarding flags.

    Raises:
        HTTPException(500): If the sysctl values cannot be read.
    """
    try:
        status = await firewall.get_sysctl()
        return SysctlResponse(success=True, message="OK", status=status)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("/sysctl", response_model=SysctlResponse)
async def set_sysctl(req: SysctlUpdateRequest, _key: str = ApiKey):
    """Enable or disable IP forwarding via sysctl.

    Sets ``net.ipv4.ip_forward`` and ``net.ipv6.conf.all.forwarding``
    to the requested values.  Changes take effect immediately but are
    not persisted across reboots unless separately configured.

    Args:
        req: Request body with IPv4 and IPv6 forward boolean flags.

    Returns:
        SysctlResponse: Updated forwarding state.

    Raises:
        HTTPException(500): If the sysctl write fails.
    """
    try:
        status = await firewall.set_sysctl(
            ip_forward=req.ip_forward,
            ip6_forward=req.ip6_forward,
        )
        return SysctlResponse(
            success=True,
            message=f"IPv4 forward={'on' if req.ip_forward else 'off'}, "
            f"IPv6 forward={'on' if req.ip6_forward else 'off'}",
            status=status,
        )
    except RuntimeError as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# ---------------------------------------------------------------------------
# NAT per-customer egress
# ---------------------------------------------------------------------------


@router.get("/nat/egress", response_model=NatEgressMapResponse)
async def get_egress_map(_key: str = ViewerKey):
    """List the per-subscriber egress NAT map.

    Returns all subscriber-IP to public-IP mappings currently active
    in the nftables NAT map.

    Returns:
        NatEgressMapResponse: List of egress mappings and total count.

    Raises:
        HTTPException(500): If the NAT map cannot be read.
    """
    try:
        entries = await nat.get_egress_map()
        return NatEgressMapResponse(entries=entries, count=len(entries))
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/nat/egress", response_model=NatEgressResponse)
async def set_egress(req: NatEgressSetRequest, _key: str = ApiKey):
    """Map a subscriber IP to a public egress IP.

    Creates an nftables NAT map entry so that traffic from the
    subscriber exits the BNG with the specified public source IP.

    Args:
        req: Request body with subscriber target IP and public IP.

    Returns:
        NatEgressResponse: Success status and confirmation message.

    Raises:
        HTTPException(400): If the mapping cannot be created.
    """
    try:
        msg = await nat.set_egress(req.target, req.public_ip)
        return NatEgressResponse(success=True, message=msg)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/nat/egress/{customer_ip}", status_code=204)
async def clear_egress(customer_ip: str = Path(pattern=RE_SAFE_IP), _key: str = ApiKey):
    """Remove a subscriber's egress NAT mapping.

    Deletes the nftables map entry for the given subscriber IP,
    reverting their traffic to the default masquerade behaviour.

    Args:
        customer_ip: The subscriber IP whose mapping should be removed.

    Raises:
        HTTPException(404): If the egress mapping does not exist.
        HTTPException(500): If the removal otherwise fails.
    """
    try:
        await nat.clear_egress(customer_ip)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if (
            "no such" in msg
            or "does not exist" in msg
            or "cannot" in msg
            or "not found" in msg
        ):
            raise HTTPException(
                status_code=404,
                detail=f"Egress mapping for '{customer_ip}' not found",
            ) from exc
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/nat/public-ip", response_model=NatEgressResponse)
async def add_public_ip(req: NatPublicIpRequest, _key: str = ApiKey):
    """Bind a public IP address to the uplink interface.

    Adds a secondary IP address to the specified network interface so
    it can be used for per-subscriber egress NAT.

    Args:
        req: Request body with the public IP and target interface name.

    Returns:
        NatEgressResponse: Success status and confirmation message.

    Raises:
        HTTPException(400): If the IP cannot be bound to the interface.
    """
    try:
        msg = await nat.add_public_ip(req.public_ip, req.interface)
        return NatEgressResponse(success=True, message=msg)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/nat/public-ip/{public_ip}",
    status_code=204,
)
async def remove_public_ip(
    public_ip: str = Path(pattern=RE_SAFE_IP), _key: str = ApiKey
):
    """Remove a public IP address from the uplink interface.

    Removes a secondary IP address previously bound for egress NAT.

    Args:
        public_ip: The public IP address to remove.

    Raises:
        HTTPException(400): If the IP cannot be removed.
    """
    try:
        await nat.remove_public_ip(public_ip)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/nat/status", response_model=NatStatusResponse)
async def full_nat_status(_key: str = ViewerKey):
    """Return comprehensive NAT status.

    Aggregates egress map entries, postrouting chain state, and
    bound public IPs into a single status response.

    Returns:
        NatStatusResponse: Egress map, postrouting rules, and bound IPs.

    Raises:
        HTTPException(500): If the NAT status cannot be retrieved.
    """
    try:
        data = await nat.nat_status()
        return NatStatusResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/nat/box-egress", response_model=BoxEgressResponse)
async def box_egress_status(_key: str = ViewerKey):
    """Check whether the accelnat table (box egress) is enabled.

    The accelnat table provides server-originated traffic NAT, separate
    from per-subscriber egress NAT.

    Returns:
        BoxEgressResponse: Enabled flag and status message.

    Raises:
        HTTPException(500): If the status cannot be determined.
    """
    try:
        data = await nat.box_egress_status()
        return BoxEgressResponse(
            success=True,
            message="OK",
            enabled=data["enabled"],
        )
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/nat/box-egress", response_model=BoxEgressResponse)
async def box_egress_toggle(req: BoxEgressRequest, _key: str = ApiKey):
    """Toggle the accelnat table on or off.

    Enables or disables the nftables table responsible for NAT on
    server-originated (box) traffic.

    Args:
        req: Request body with action (``on`` or ``off``).

    Returns:
        BoxEgressResponse: Updated enabled state and message.

    Raises:
        HTTPException(400): If the action value is invalid.
        HTTPException(500): If the toggle operation fails.
    """
    try:
        msg = await nat.box_egress_set(req.action)
        enabled = req.action == "on"
        return BoxEgressResponse(
            success=True,
            message=msg,
            enabled=enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# ---------------------------------------------------------------------------
# Conntrack
# ---------------------------------------------------------------------------


@router.get("/conntrack", response_model=ConntrackResponse)
async def conntrack_status(_key: str = ViewerKey):
    """Return the ``nf_conntrack_max`` setting and current usage.

    Reads the kernel conntrack table size limit and the number of
    entries currently in use.

    Returns:
        ConntrackResponse: Max value, current count, and utilisation.

    Raises:
        HTTPException(500): If the conntrack status cannot be read.
    """
    try:
        data = await diagnostics.get_conntrack()
        return ConntrackResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("/conntrack", response_model=ConntrackResponse)
async def conntrack_tune(
    req: ConntrackUpdateRequest,
    _key: str = ApiKey,
):
    """Set ``nf_conntrack_max`` and persist across reboots.

    Updates the kernel conntrack table size limit and writes the value
    to sysctl configuration for persistence.

    Args:
        req: Request body with the desired max_value.

    Returns:
        ConntrackResponse: Updated conntrack configuration.

    Raises:
        HTTPException(500): If the sysctl update fails.
    """
    try:
        data = await diagnostics.set_conntrack(req.max_value)
        return ConntrackResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


# ---------------------------------------------------------------------------
# SNMP
# ---------------------------------------------------------------------------


@router.get("/snmp", response_model=SnmpStatusResponse)
async def snmp_status(_key: str = ViewerKey):
    """Check SNMP daemon status and UDP port availability.

    Verifies whether the SNMP daemon (snmpd) is running and whether
    UDP port 161 is open and listening.

    Returns:
        SnmpStatusResponse: Running flag, port status, and detail text.

    Raises:
        HTTPException(500): If the SNMP status check fails.
    """
    try:
        data = await diagnostics.snmp_status()
        return SnmpStatusResponse(
            running=data.get("status") == "ok",
            port_open="port 161 open" in data.get("detail", ""),
            detail=data.get("detail", ""),
        )
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
