"""Bulk operations endpoint — batch commands across multiple sessions.

Exposes endpoints that accept arrays of targets and execute the
underlying operation for each item, returning per-item results.

All bulk endpoints require ``operator`` role or higher because they
perform write operations.  The maximum batch size is enforced at the
request model layer (100 items per call).
"""

from __future__ import annotations

from fastapi import APIRouter

from ..auth import OperatorKey
from ..models.schemas import (
    BulkOperationResponse,
    BulkRateLimitRequest,
    BulkResultItem,
    BulkShaperRestoreRequest,
    BulkTerminateRequest,
)
from ..services import bulk

router = APIRouter(prefix="/api/v1/bulk", tags=["bulk"])


@router.post("/terminate", response_model=BulkOperationResponse)
async def bulk_terminate(
    req: BulkTerminateRequest,
    _key: str = OperatorKey,
) -> BulkOperationResponse:
    """Terminate multiple subscriber sessions in a single request.

    Accepts a list of usernames and disconnects each session
    independently.  Individual failures do not cancel the remaining
    items.

    Args:
        req: Request body with list of usernames to terminate.

    Returns:
        BulkOperationResponse: Per-item results with overall counts.
    """
    raw = await bulk.bulk_terminate(req.usernames)
    items = [BulkResultItem(**r) for r in raw]
    ok = sum(1 for i in items if i.success)
    return BulkOperationResponse(
        operation="terminate",
        total=len(items),
        succeeded=ok,
        failed=len(items) - ok,
        results=items,
    )


@router.post("/ratelimit", response_model=BulkOperationResponse)
async def bulk_ratelimit(
    req: BulkRateLimitRequest,
    _key: str = OperatorKey,
) -> BulkOperationResponse:
    """Change rate limits for multiple subscribers in a single request.

    Accepts a list of username-rate pairs and applies each shaper
    change independently.

    Args:
        req: Request body with list of rate-limit items.

    Returns:
        BulkOperationResponse: Per-item results with overall counts.
    """
    payload = [{"username": i.username, "rate": i.rate} for i in req.items]
    raw = await bulk.bulk_ratelimit(payload)
    items = [BulkResultItem(**r) for r in raw]
    ok = sum(1 for i in items if i.success)
    return BulkOperationResponse(
        operation="ratelimit",
        total=len(items),
        succeeded=ok,
        failed=len(items) - ok,
        results=items,
    )


@router.post("/shaper-restore", response_model=BulkOperationResponse)
async def bulk_shaper_restore(
    req: BulkShaperRestoreRequest,
    _key: str = OperatorKey,
) -> BulkOperationResponse:
    """Restore RADIUS-assigned shapers for multiple subscribers.

    Accepts a list of usernames and restores each session's original
    shaper independently.

    Args:
        req: Request body with list of usernames to restore.

    Returns:
        BulkOperationResponse: Per-item results with overall counts.
    """
    raw = await bulk.bulk_shaper_restore(req.usernames)
    items = [BulkResultItem(**r) for r in raw]
    ok = sum(1 for i in items if i.success)
    return BulkOperationResponse(
        operation="shaper-restore",
        total=len(items),
        succeeded=ok,
        failed=len(items) - ok,
        results=items,
    )
