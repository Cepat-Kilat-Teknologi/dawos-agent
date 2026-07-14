"""PPPoE runtime configuration — scalar keys in the ``[pppoe]`` section.

Manages ``service-name``, ``ac-name``, and ``verbose`` settings that
control PPPoE protocol behaviour.  Interface bindings are handled
separately by :mod:`~dawos_agent.services.pppoe`, and PADO delay by
:mod:`~dawos_agent.services.pado_delay`.

All write operations create a config backup before modifying the file.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config import ACCEL_CONFIG
from . import config_manager

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

#: Keys we manage — mapped to their Python-safe attribute names.
_KEY_MAP: dict[str, str] = {
    "service-name": "service_name",
    "ac-name": "ac_name",
    "verbose": "verbose",
}


def _parse_pppoe_runtime(content: str) -> dict[str, Any]:
    """Extract scalar runtime keys from the ``[pppoe]`` section.

    Only ``service-name``, ``ac-name``, and ``verbose`` are extracted.
    Other keys (``interface=``, ``pado-delay=``, etc.) are ignored —
    they are managed by their own dedicated services.

    Args:
        content: Full ``accel-ppp.conf`` file content.

    Returns:
        A dictionary with ``service_name`` (str), ``ac_name`` (str),
        and ``verbose`` (int).
    """
    result: dict[str, Any] = {
        "service_name": "",
        "ac_name": "",
        "verbose": 0,
    }

    in_pppoe = False

    for raw_line in content.splitlines():
        stripped = raw_line.strip()

        # Section headers
        if stripped.startswith("["):
            in_pppoe = stripped.lower() == "[pppoe]"
            continue

        if not in_pppoe or not stripped or stripped.startswith("#"):
            continue

        if "=" not in stripped:
            continue

        key, _, val = stripped.partition("=")
        key = key.strip().lower()
        val = val.strip()

        if key == "service-name":
            result["service_name"] = val
        elif key == "ac-name":
            result["ac_name"] = val
        elif key == "verbose":
            result["verbose"] = int(val) if val.isdigit() else 0

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_pppoe_runtime_config(
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Read PPPoE runtime settings from the ``[pppoe]`` section.

    Args:
        config_path: Override the default configuration file path.

    Returns:
        A dictionary suitable for constructing
        :class:`~dawos_agent.models.schemas.PppoeRuntimeConfigResponse`.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    return _parse_pppoe_runtime(content)


def set_pppoe_runtime_config(  # pylint: disable=too-many-branches,too-many-locals
    *,
    service_name: str | None = None,
    ac_name: str | None = None,
    verbose: int | None = None,
    config_path: Path | None = None,
) -> str:
    """Update PPPoE runtime settings in the ``[pppoe]`` section.

    Only non-``None`` arguments are written; unspecified keys are left
    unchanged.  Creates a config backup before writing.

    Args:
        service_name: New PPPoE service name (or ``None`` to keep current).
        ac_name: New Access Concentrator name (or ``None`` to keep current).
        verbose: Verbose logging flag 0/1 (or ``None`` to keep current).
        config_path: Override the default configuration file path.

    Returns:
        A confirmation message string.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If all arguments are ``None`` (nothing to update).
    """
    if service_name is None and ac_name is None and verbose is None:
        raise ValueError("At least one field must be provided")

    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    # Map of config-key -> new-value for the keys we need to update
    updates: dict[str, str] = {}
    if service_name is not None:
        updates["service-name"] = service_name
    if ac_name is not None:
        updates["ac-name"] = ac_name
    if verbose is not None:
        updates["verbose"] = str(verbose)

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    out: list[str] = []
    in_pppoe = False
    keys_set: set[str] = set()

    for raw in lines:
        line = raw.strip()

        if line.startswith("["):
            # Leaving [pppoe] — append any keys we haven't replaced yet
            if in_pppoe:
                for ukey, uval in updates.items():
                    if ukey not in keys_set:
                        out.append(f"{ukey}={uval}")
                        keys_set.add(ukey)

            in_pppoe = line.lower() == "[pppoe]"
            out.append(raw)
            continue

        if in_pppoe and "=" in line:
            key, _, _ = line.partition("=")
            key_lower = key.strip().lower()

            if key_lower in updates:
                out.append(f"{key_lower}={updates[key_lower]}")
                keys_set.add(key_lower)
                continue

        out.append(raw)

    # [pppoe] at EOF — append missing keys
    if in_pppoe:
        for ukey, uval in updates.items():
            if ukey not in keys_set:
                out.append(f"{ukey}={uval}")
                keys_set.add(ukey)

    new_content = "\n".join(out) + "\n"
    config_manager.write_config(new_content, backup=True)

    changed = ", ".join(f"{k}={v}" for k, v in updates.items())
    log.info("Updated PPPoE runtime config: %s", changed)
    return f"PPPoE config updated: {changed}"
