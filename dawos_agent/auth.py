"""API-key authentication for the dawos-agent REST API.

Implements a simple shared-secret authentication model using a static
API key transmitted via the ``X-API-Key`` HTTP header.  Every request
except the public health-check endpoint must include this header.

The expected key value is read from :pydata:`dawos_agent.config.settings.api_key`
(environment variable ``DAWOS_API_KEY``).  In production deployments
this should be a cryptographically random string rotated periodically.

Usage in routers::

    from dawos_agent.auth import ApiKey

    router = APIRouter(dependencies=[ApiKey])
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import settings

# Declare the header scheme once; ``auto_error=False`` allows the
# dependency to return *None* instead of raising a 403 so we can
# provide a custom 401 response with a clearer error message.
_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Security(_header)) -> str:
    """FastAPI dependency that enforces API-key authentication.

    Extracts the ``X-API-Key`` header value and compares it against the
    configured secret.  Returns the validated key string on success so
    downstream dependencies can inspect it if needed.

    Raises:
        HTTPException: 401 Unauthorized if the key is missing or does
            not match the expected value.
    """
    if key is None or key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return key


# Re-export as a FastAPI dependency for convenient use in routers.
ApiKey = Depends(require_api_key)  # pylint: disable=invalid-name
