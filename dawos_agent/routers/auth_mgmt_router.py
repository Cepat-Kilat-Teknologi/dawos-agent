"""Authentication management endpoints (admin-only).

Provides tooling for API key lifecycle management:

* ``POST /api/v1/auth/generate-key`` — generate a cryptographically
  secure API key suitable for use in ``DAWOS_API_KEY`` or the RBAC
  keys file.  The key is returned once and never stored server-side.
* ``GET /api/v1/auth/rbac-status`` — inspect whether multi-key RBAC
  is active and how many keys are loaded.

Both endpoints require admin-level access (DAWOS-16).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter

from ..auth import AdminKey, get_resolver
from ..models.schemas import GenerateKeyResponse, RbacStatusResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/generate-key",
    response_model=GenerateKeyResponse,
    summary="Generate a new API key",
    description=(
        "Generate a cryptographically secure API key (32-byte URL-safe "
        "base64).  The key is returned once in the response body and is "
        "never stored on the server.  Use the generated key to update "
        "``DAWOS_API_KEY`` or the RBAC keys file (DAWOS-16)."
    ),
)
async def generate_key(
    _key: str = AdminKey,  # noqa: ARG001  # pylint: disable=unused-argument
) -> GenerateKeyResponse:
    """Generate a random API key suitable for production use.

    Returns:
        GenerateKeyResponse: Contains the generated key and usage hints.
    """
    new_key = secrets.token_urlsafe(32)
    return GenerateKeyResponse(
        key=new_key,
        hint="Update DAWOS_API_KEY or add to the RBAC keys file, then restart.",
    )


@router.get(
    "/rbac-status",
    response_model=RbacStatusResponse,
    summary="RBAC key status",
    description=(
        "Returns whether multi-key RBAC is active and the number of "
        "loaded keys (excluding the primary key).  Useful for verifying "
        "that the keys file was parsed correctly after deployment."
    ),
)
async def rbac_status(
    _key: str = AdminKey,  # noqa: ARG001  # pylint: disable=unused-argument
) -> RbacStatusResponse:
    """Return the current RBAC configuration status.

    Returns:
        RbacStatusResponse: RBAC status including key count.
    """
    resolver = get_resolver()
    return RbacStatusResponse(
        rbac_enabled=resolver.rbac_enabled,
        extra_keys_count=len(resolver.extra_keys),
    )
