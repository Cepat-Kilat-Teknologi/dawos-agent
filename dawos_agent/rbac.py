"""Role-based access control for the dawos-agent REST API.

Defines three hierarchical roles — ``viewer``, ``operator``, and
``admin`` — and provides key resolution logic that maps API keys to
roles.  The role hierarchy determines which endpoints each key can
access:

* **viewer** — read-only GET endpoints (monitoring, dashboards).
* **operator** — all viewer access plus write operations (session
  management, firewall, NAT, PPPoE configuration).
* **admin** — full access including destructive operations (service
  restart, config apply, checkpoint rollback).

Key resolution order:

1. Check the optional keys file (``DAWOS_API_KEYS_FILE``).
2. Fall back to the primary ``DAWOS_API_KEY`` (always admin role).

When no keys file is configured, the agent operates in single-key mode
and all authenticated requests have admin privileges — identical to the
pre-RBAC behaviour.
"""

from __future__ import annotations

import enum
import json
import logging
import secrets
from pathlib import Path

log = logging.getLogger(__name__)


class Role(str, enum.Enum):
    """Access role with hierarchical privilege levels.

    Roles are ordered from least to most privileged.  A key with a
    higher-privilege role can access all endpoints available to
    lower-privilege roles.

    Attributes:
        VIEWER: Read-only access to GET endpoints.
        OPERATOR: Read and write access (excludes destructive admin
            operations like service restart and config apply).
        ADMIN: Full access to all endpoints.
    """

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


#: Numeric weight for each role — higher means more privilege.
_ROLE_WEIGHT: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.OPERATOR: 1,
    Role.ADMIN: 2,
}


def role_has_access(user_role: Role, required_role: Role) -> bool:
    """Check whether *user_role* meets or exceeds *required_role*.

    Args:
        user_role: The role resolved from the API key.
        required_role: The minimum role needed by the endpoint.

    Returns:
        ``True`` if access should be granted.
    """
    return _ROLE_WEIGHT[user_role] >= _ROLE_WEIGHT[required_role]


def load_keys_file(path: str) -> dict[str, Role]:
    """Load API key to role mappings from a JSON file.

    The file must contain a JSON object mapping key strings to role
    names::

        {
            "monitoring-key-abc": "viewer",
            "automation-key-xyz": "operator",
            "super-admin-key-123": "admin"
        }

    Args:
        path: Filesystem path to the JSON keys file.

    Returns:
        A dictionary mapping API key strings to :class:`Role` values.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If the file contains invalid JSON or unknown role
            names.
    """
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)

    if not isinstance(data, dict):
        raise ValueError(
            f"Keys file must contain a JSON object, got {type(data).__name__}"
        )

    keys: dict[str, Role] = {}
    valid_roles = {r.value for r in Role}

    for key, role_name in data.items():
        if not isinstance(role_name, str) or role_name not in valid_roles:
            raise ValueError(
                f"Invalid role '{role_name}' for key ending '...{key[-4:]}'. "
                f"Valid roles: {', '.join(sorted(valid_roles))}"
            )
        keys[str(key)] = Role(role_name)

    return keys


class KeyResolver:
    """Resolve API keys to roles using the configured key sources.

    Checks the optional keys file first, then falls back to the
    primary ``DAWOS_API_KEY`` (which always maps to admin).

    Attributes:
        extra_keys: Additional key-to-role mappings loaded from the
            keys file.  Empty when no keys file is configured.
    """

    def __init__(self, primary_key: str, keys_file: str | None = None) -> None:
        self._primary_key = primary_key
        self.extra_keys: dict[str, Role] = {}

        if keys_file:
            try:
                self.extra_keys = load_keys_file(keys_file)
                log.info(
                    "RBAC keys file loaded: %d key(s) from %s",
                    len(self.extra_keys),
                    keys_file,
                )
            except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
                log.error("Failed to load RBAC keys file %s: %s", keys_file, exc)

    def resolve(self, api_key: str) -> Role | None:
        """Determine the role for the given API key.

        Args:
            api_key: The key value from the ``X-API-Key`` header.

        Returns:
            The resolved :class:`Role`, or ``None`` if the key is not
            recognised by any source.
        """
        # Constant-time comparison against every known key to avoid
        # leaking key material through byte-wise timing differences.
        candidate = api_key.encode("utf-8")

        # Check extra keys first (keys file).
        for known_key, role in self.extra_keys.items():
            if secrets.compare_digest(candidate, known_key.encode("utf-8")):
                return role

        # Fall back to primary key (always admin).
        if secrets.compare_digest(candidate, self._primary_key.encode("utf-8")):
            return Role.ADMIN

        return None

    @property
    def rbac_enabled(self) -> bool:
        """Whether multi-key RBAC is active.

        Returns ``True`` when a keys file has been loaded with at least
        one entry.  When ``False``, the agent operates in single-key
        mode (all authenticated requests are admin).
        """
        return bool(self.extra_keys)
