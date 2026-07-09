"""Audit log endpoint — admin-only access to the in-memory audit trail.

Exposes the ring buffer populated by
:class:`~dawos_agent.middleware.AuditLogMiddleware` as a paginated,
filterable JSON endpoint.  Only users with the ``admin`` RBAC role can
view audit entries.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..auth import AdminKey
from ..middleware import audit_buffer
from ..models.schemas import AuditEntry, AuditListResponse

router = APIRouter(prefix="/api/v1", tags=["audit"])


@router.get("/audit", response_model=AuditListResponse)
async def list_audit_entries(
    limit: int = Query(100, ge=1, le=1000, description="Maximum entries to return"),
    method: str | None = Query(None, description="Filter by HTTP method"),
    path: str | None = Query(None, description="Filter by path prefix"),
    role: str | None = Query(None, description="Filter by RBAC role"),
    status: int | None = Query(None, description="Filter by status code"),
    _key: str = AdminKey,
) -> AuditListResponse:
    """List recent audit log entries from the in-memory ring buffer.

    Returns the most recent mutating HTTP requests (POST, PUT, PATCH,
    DELETE) recorded by the audit middleware.  Results are ordered
    newest-first and can be filtered by method, path prefix, role,
    or status code.

    This endpoint requires ``admin`` role access.

    Args:
        limit: Maximum number of entries to return (1-1000, default 100).
        method: Filter to entries matching this HTTP method (case-insensitive).
        path: Filter to entries whose path starts with this prefix.
        role: Filter to entries from callers with this RBAC role.
        status: Filter to entries with this HTTP status code.

    Returns:
        AuditListResponse: Count, buffer capacity, and matching entries.
    """
    entries = list(audit_buffer)

    # Apply optional filters.
    if method:
        method_upper = method.upper()
        entries = [e for e in entries if e["method"] == method_upper]
    if path:
        entries = [e for e in entries if e["path"].startswith(path)]
    if role:
        entries = [e for e in entries if e["role"] == role]
    if status is not None:
        entries = [e for e in entries if e["status"] == status]

    # Newest first, apply limit.
    entries = list(reversed(entries))[:limit]

    return AuditListResponse(
        count=len(entries),
        buffer_size=audit_buffer.maxlen or 0,
        entries=[AuditEntry(**e) for e in entries],
    )
