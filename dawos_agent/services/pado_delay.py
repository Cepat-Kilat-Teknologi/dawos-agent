"""PADO delay — PPPoE Active Discovery Offer timing.

Controls the delay before accel-ppp sends a PADO response to a client's
PADI request.  Useful for load balancing across multiple BNGs — a BNG
with lower PADO delay wins the client.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..config import ACCEL_CONFIG
from . import config_manager

log = logging.getLogger(__name__)


def get_pado_delay(config_path: Path | None = None) -> dict:
    """Read the PADO delay settings from the ``[pppoe]`` section.

    Args:
        config_path: Override the default configuration file path.

    Returns:
        A dictionary with ``delay`` (ms), ``min_sessions``, and a
        human-readable ``description``.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    in_pppoe = False
    delay = 0
    min_sessions = 0

    for raw in content.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_pppoe = line.lower() == "[pppoe]"
            continue

        if not in_pppoe:
            continue

        m = re.match(r"pado-delay\s*=\s*(\d+)", line, re.IGNORECASE)
        if m:
            delay = int(m.group(1))
        m = re.match(r"pado-delay-sessions\s*=\s*(\d+)", line, re.IGNORECASE)
        if m:
            min_sessions = int(m.group(1))

    return {
        "delay": delay,
        "min_sessions": min_sessions,
        "description": (
            f"PADO delayed by {delay}ms after {min_sessions} sessions"
            if delay > 0
            else "No PADO delay configured"
        ),
    }


def set_pado_delay(  # pylint: disable=too-many-branches
    delay: int,
    min_sessions: int = 0,
    config_path: Path | None = None,
) -> str:
    """Set the PADO delay in the ``[pppoe]`` section.

    Creates a backup before writing.

    Args:
        delay: Delay in milliseconds (0 to disable).
        min_sessions: Only apply delay after this many active sessions.
        config_path: Override the default configuration file path.

    Returns:
        A confirmation message string.

    Raises:
        ValueError: If *delay* is negative.
        FileNotFoundError: If the configuration file does not exist.
    """
    if delay < 0:
        raise ValueError("PADO delay cannot be negative")

    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    out: list[str] = []
    in_pppoe = False
    delay_set = False
    sessions_set = False

    for raw in lines:
        line = raw.strip()
        if line.startswith("["):
            if in_pppoe:
                if not delay_set:
                    out.append(f"pado-delay={delay}")
                if not sessions_set and min_sessions > 0:
                    out.append(f"pado-delay-sessions={min_sessions}")
            in_pppoe = line.lower() == "[pppoe]"
            delay_set = False
            sessions_set = False
            out.append(raw)
            continue

        if in_pppoe:
            if re.match(r"pado-delay\s*=", line, re.IGNORECASE):
                out.append(f"pado-delay={delay}")
                delay_set = True
                continue
            if re.match(r"pado-delay-sessions\s*=", line, re.IGNORECASE):
                if min_sessions > 0:
                    out.append(f"pado-delay-sessions={min_sessions}")
                sessions_set = True
                continue

        out.append(raw)

    # [pppoe] at EOF
    if in_pppoe:
        if not delay_set:
            out.append(f"pado-delay={delay}")
        if not sessions_set and min_sessions > 0:
            out.append(f"pado-delay-sessions={min_sessions}")

    new_content = "\n".join(out) + "\n"
    config_manager.write_config(new_content, backup=True)
    log.info("Set PADO delay=%dms min_sessions=%d", delay, min_sessions)
    return f"PADO delay set to {delay}ms"
