"""API-key authentication with role-based access control.

Provides three access-level dependencies for use in routers:

* :data:`ViewerKey` — read-only endpoints (GET).
* :data:`OperatorKey` — read + write endpoints (most POST/PUT/DELETE).
* :data:`AdminKey` — destructive operations (service restart, config
  apply, checkpoint rollback).

When ``DAWOS_API_KEYS_FILE`` is not configured, the agent operates in
single-key mode: the primary ``DAWOS_API_KEY`` grants admin access to
all endpoints — identical to the pre-RBAC behaviour.

When a keys file **is** configured, each API key is mapped to a role
(``viewer``, ``operator``, ``admin``).  The primary ``DAWOS_API_KEY``
always retains admin access regardless of the keys file content.

Usage in routers::

    from dawos_agent.auth import ViewerKey, OperatorKey, AdminKey

    @router.get("/data")
    async def get_data(_key: str = ViewerKey):
        ...

    @router.post("/data")
    async def create_data(req: Model, _key: str = OperatorKey):
        ...

    @router.post("/apply")
    async def apply_config(req: Model, _key: str = AdminKey):
        ...
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from .config import settings
from .rbac import KeyResolver, Role, role_has_access

# Declare the header scheme once; ``auto_error=False`` allows the
# dependency to return *None* instead of raising a 403 so we can
# provide a custom 401 response with a clearer error message.
_header = APIKeyHeader(name="X-API-Key", auto_error=False)

#: Singleton resolver initialised at import time from settings.
_resolver = KeyResolver(
    primary_key=settings.api_key,
    keys_file=settings.api_keys_file or None,
)


def get_resolver() -> KeyResolver:
    """Return the active key resolver (useful for testing)."""
    return _resolver


def _require_role(min_role: Role):
    """Build a FastAPI dependency that enforces a minimum RBAC role.

    The returned coroutine:

    1. Extracts the ``X-API-Key`` header.
    2. Resolves the key to a :class:`~dawos_agent.rbac.Role`.
    3. Verifies the role meets or exceeds *min_role*.
    4. Stores the resolved role on ``request.state.role`` for
       downstream use (audit logging, etc.).
    5. Returns the validated key string.

    Args:
        min_role: The minimum role required by the endpoint.

    Returns:
        An async FastAPI dependency function.
    """

    async def dependency(
        request: Request,
        key: str | None = Security(_header),
    ) -> str:
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
            )

        resolved = _resolver.resolve(key)

        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key",
            )

        if not role_has_access(resolved, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: requires {min_role.value} role",
            )

        # Store role on request state for audit middleware / logging.
        request.state.role = resolved.value

        return key

    return dependency


# Pre-built dependencies for the three access tiers.
ViewerKey = Depends(_require_role(Role.VIEWER))  # pylint: disable=invalid-name
OperatorKey = Depends(_require_role(Role.OPERATOR))  # pylint: disable=invalid-name
AdminKey = Depends(_require_role(Role.ADMIN))  # pylint: disable=invalid-name

# Backward compatibility alias — existing routers that import ApiKey
# continue to work.  Maps to OperatorKey (read+write) which covers
# the majority of endpoints.  Admin-only endpoints must be updated
# to use AdminKey explicitly.
ApiKey = OperatorKey  # pylint: disable=invalid-name
