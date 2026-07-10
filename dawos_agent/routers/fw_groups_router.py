"""Firewall group management API endpoints.

Provides REST endpoints for creating, deleting, and managing nftables
named sets (address groups, network groups, and port groups) used by
firewall rules on the BNG host.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    AddMembersRequest,
    CreateGroupRequest,
    FirewallGroupListResponse,
    GroupActionResponse,
    MemberActionResponse,
)
from ..services import firewall_groups

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/firewall/groups", tags=["firewall-groups"])


@router.get("", response_model=FirewallGroupListResponse)
async def list_groups(_key: str = ViewerKey):
    """List all firewall groups.

    Returns every named nftables set currently defined, including the
    group type (address, network, or port) and its members.

    Returns:
        FirewallGroupListResponse: List of groups with member details.

    Raises:
        HTTPException(500): If the group list cannot be retrieved.
    """
    try:
        data = await firewall_groups.list_groups()
        return FirewallGroupListResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("", status_code=201, response_model=GroupActionResponse)
async def create_group(req: CreateGroupRequest, _key: str = ApiKey):
    """Create a new firewall group.

    Creates a named nftables set of the specified type and optionally
    populates it with initial elements.

    Args:
        req: Request body with group name, type, and optional elements.

    Returns:
        GroupActionResponse: Success status and created group details.

    Raises:
        HTTPException(400): If the group type or elements are invalid.
        HTTPException(500): If the nftables command fails.
    """
    try:
        data = await firewall_groups.create_group(
            req.name, req.group_type, elements=req.elements or None
        )
        return GroupActionResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if "exists" in str(exc).lower():
            raise HTTPException(
                status_code=409, detail=f"Group '{req.name}' already exists"
            ) from exc
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.delete("/{name}", status_code=204)
async def delete_group(name: str, _key: str = ApiKey):
    """Delete a firewall group by name.

    Removes the named nftables set and all its members.

    Args:
        name: The group name to delete.

    Raises:
        HTTPException(500): If the group cannot be deleted.
    """
    try:
        await firewall_groups.delete_group(name)
    except Exception as exc:
        msg = str(exc).lower()
        if "no such" in msg or "does not exist" in msg:
            raise HTTPException(
                status_code=404, detail=f"Group '{name}' not found"
            ) from exc
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/{name}/members", response_model=MemberActionResponse)
async def add_members(name: str, req: AddMembersRequest, _key: str = ApiKey):
    """Add members to an existing firewall group.

    Appends the provided elements (IPs, networks, or ports) to the
    named nftables set.

    Args:
        name: The group name to add members to.
        req: Request body with the list of elements to add.

    Returns:
        MemberActionResponse: Success status and confirmation message.

    Raises:
        HTTPException(500): If the members cannot be added.
    """
    try:
        data = await firewall_groups.add_members(name, req.elements)
        return MemberActionResponse(**data)
    except Exception as exc:
        log.error("Operation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
