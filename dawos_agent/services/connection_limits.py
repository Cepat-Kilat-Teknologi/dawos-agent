"""Connection limits management for accel-ppp sessions.

Provides read and write access to per-interface and global session
limits within the accel-ppp configuration file.  Supports max-sessions,
max-starting, session-timeout, and per-interface PADI rate limiting.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..config import ACCEL_CONFIG
from . import config_manager

log = logging.getLogger(__name__)


def get_limits(config_path: Path | None = None) -> dict:
    """Read global session limits from the accel-ppp configuration.

    Parses the ``[pppoe]`` and ``[common]``/``[general]`` sections for
    ``max-sessions``, ``max-starting``, and ``session-timeout`` values.

    Args:
        config_path: Override the default configuration file path.

    Returns:
        A dictionary with ``max_sessions``, ``max_starting``, and
        ``session_timeout`` integer values.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    result: dict = {
        "max_sessions": 0,
        "max_starting": 0,
        "session_timeout": 0,
    }

    in_pppoe = False
    in_general = False

    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_pppoe = line.lower() == "[pppoe]"
            in_general = line.lower() == "[common]" or line.lower() == "[general]"
            continue

        if in_pppoe:
            m = re.match(r"max-sessions\s*=\s*(\d+)", line, re.IGNORECASE)
            if m:
                result["max_sessions"] = int(m.group(1))
            m = re.match(r"max-starting\s*=\s*(\d+)", line, re.IGNORECASE)
            if m:
                result["max_starting"] = int(m.group(1))

        if in_general:
            m = re.match(r"session-timeout\s*=\s*(\d+)", line, re.IGNORECASE)
            if m:
                result["session_timeout"] = int(m.group(1))

    return result


def set_limits(
    *,
    max_sessions: int | None = None,
    max_starting: int | None = None,
    config_path: Path | None = None,
) -> str:
    """Update global session limits in the ``[pppoe]`` section.

    Modifies existing values in-place or appends them if not present.
    Creates a backup before writing.

    Args:
        max_sessions: Maximum concurrent sessions allowed.
        max_starting: Maximum sessions in the starting state.
        config_path: Override the default configuration file path.

    Returns:
        A human-readable confirmation message.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    out: list[str] = []
    in_pppoe = False
    ms_set = False
    mst_set = False

    for raw in lines:
        line = raw.strip()
        if line.startswith("["):
            # Leaving [pppoe] — inject missing keys
            if in_pppoe:
                if max_sessions is not None and not ms_set:
                    out.append(f"max-sessions={max_sessions}")
                if max_starting is not None and not mst_set:
                    out.append(f"max-starting={max_starting}")
            in_pppoe = line.lower() == "[pppoe]"
            ms_set = False
            mst_set = False
            out.append(raw)
            continue

        if in_pppoe:
            if max_sessions is not None and re.match(
                r"max-sessions\s*=",
                line,
                re.IGNORECASE,
            ):
                out.append(f"max-sessions={max_sessions}")
                ms_set = True
                continue
            if max_starting is not None and re.match(
                r"max-starting\s*=",
                line,
                re.IGNORECASE,
            ):
                out.append(f"max-starting={max_starting}")
                mst_set = True
                continue

        out.append(raw)

    # If [pppoe] is the last section, inject missing keys at EOF
    if in_pppoe:
        if max_sessions is not None and not ms_set:
            out.append(f"max-sessions={max_sessions}")
        if max_starting is not None and not mst_set:
            out.append(f"max-starting={max_starting}")

    new_content = "\n".join(out) + "\n"
    config_manager.write_config(new_content, backup=True)
    log.info(
        "Updated connection limits: max_sessions=%s max_starting=%s",
        max_sessions,
        max_starting,
    )
    return "Connection limits updated"


def get_interface_limit(interface: str, config_path: Path | None = None) -> dict:
    """Read the PADI rate limit for a specific PPPoE interface.

    Args:
        interface: Interface name (e.g. ``eth0.100``).
        config_path: Override the default configuration file path.

    Returns:
        A dictionary with ``interface``, ``padi_limit``, and ``found``
        (boolean indicating whether the interface was found).

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    in_pppoe = False

    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_pppoe = line.lower() == "[pppoe]"
            continue
        if in_pppoe and line.startswith("interface="):
            val = line.split("=", 1)[1].strip()
            parts = val.split(",")
            name = parts[0].strip()
            if name == interface:
                padi_limit = 0
                for p in parts[1:]:
                    kv = p.strip().split("=", 1)
                    if len(kv) == 2 and kv[0].strip() == "padi-limit":
                        padi_limit = int(kv[1].strip())
                return {
                    "interface": interface,
                    "padi_limit": padi_limit,
                    "found": True,
                }

    return {"interface": interface, "padi_limit": 0, "found": False}
