"""PPPoE interface binding — manage ``[pppoe]`` section in accel-ppp.conf.

The ``[pppoe]`` section uses **duplicate** ``interface=`` keys, one per
listening interface::

    [pppoe]
    interface=eth0.100
    interface=eth0.200,padi-limit=0
    verbose=1

Python's :mod:`configparser` can't handle duplicate keys, so we parse
the config file line-by-line.  After every mutation we back up the
config via :mod:`config_manager` and reload accel-ppp.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from ..config import ACCEL_CONFIG
from ..models.schemas import PppoeInterface
from . import config_manager

log = logging.getLogger(__name__)

# Regex for ``interface=<name>[,<options>]`` inside [pppoe]
_IFACE_RE = re.compile(r"^interface\s*=\s*(.+)$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_pppoe_interfaces(content: str) -> list[PppoeInterface]:
    """Extract ``interface=`` lines from the ``[pppoe]`` section.

    Args:
        content: The full accel-ppp configuration file text.

    Returns:
        A list of :class:`PppoeInterface` objects.
    """
    interfaces: list[PppoeInterface] = []
    in_pppoe = False

    for raw_line in content.splitlines():
        line = raw_line.strip()

        # Track section boundaries
        if line.startswith("["):
            in_pppoe = line.lower() == "[pppoe]"
            continue

        if not in_pppoe:
            continue

        m = _IFACE_RE.match(line)
        if m:
            value = m.group(1).strip()
            # Format: "eth0.100" or "eth0.100,padi-limit=0"
            parts = value.split(",", 1)
            name = parts[0].strip()
            options = parts[1].strip() if len(parts) > 1 else ""
            interfaces.append(PppoeInterface(name=name, options=options))

    return interfaces


def _rebuild_config(  # pylint: disable=too-many-branches
    content: str,
    interfaces: list[PppoeInterface],
) -> str:
    """Rebuild the configuration with updated ``interface=`` lines.

    Replaces all existing ``interface=`` lines in the ``[pppoe]``
    section with the provided list.

    Args:
        content: The full accel-ppp configuration file text.
        interfaces: The desired list of PPPoE interfaces.

    Returns:
        The rebuilt configuration file content.
    """
    out_lines: list[str] = []
    in_pppoe = False
    iface_lines_written = False

    for raw_line in content.splitlines():
        line = raw_line.strip()

        # Detect section transitions
        if line.startswith("["):
            # If leaving [pppoe], flush interface lines we haven't written yet
            if in_pppoe and not iface_lines_written:
                for iface in interfaces:
                    val = iface.name
                    if iface.options:
                        val += f",{iface.options}"
                    out_lines.append(f"interface={val}")
                iface_lines_written = True

            in_pppoe = line.lower() == "[pppoe]"
            if in_pppoe:
                iface_lines_written = False
            out_lines.append(raw_line)
            continue

        if in_pppoe and _IFACE_RE.match(line):
            # Skip old interface= lines — we'll write fresh ones
            if not iface_lines_written:
                for iface in interfaces:
                    val = iface.name
                    if iface.options:
                        val += f",{iface.options}"
                    out_lines.append(f"interface={val}")
                iface_lines_written = True
            continue

        out_lines.append(raw_line)

    # Edge case: [pppoe] is the last section and had no interface= lines
    if in_pppoe and not iface_lines_written:
        for iface in interfaces:
            val = iface.name
            if iface.options:
                val += f",{iface.options}"
            out_lines.append(f"interface={val}")

    return "\n".join(out_lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_pppoe_interfaces(config_path: Path | None = None) -> list[PppoeInterface]:
    """List PPPoE listener interfaces from the accel-ppp configuration.

    Args:
        config_path: Override the default configuration file path.

    Returns:
        A list of :class:`PppoeInterface` objects.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    content = path.read_text(encoding="utf-8")
    return _parse_pppoe_interfaces(content)


def add_pppoe_interface(
    interface: str,
    options: str = "",
    config_path: Path | None = None,
) -> str:
    """Add an interface to the ``[pppoe]`` section.

    Creates a backup before writing.

    Args:
        interface: Interface name (e.g. ``eth0.100``).
        options: Optional comma-separated options (e.g. ``padi-limit=0``).
        config_path: Override the default configuration file path.

    Returns:
        A confirmation message string.

    Raises:
        ValueError: If the interface already exists in the section.
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    content = path.read_text(encoding="utf-8")
    current = _parse_pppoe_interfaces(content)

    # Check for duplicates
    existing_names = [i.name for i in current]
    if interface in existing_names:
        raise ValueError(f"Interface {interface} already exists in [pppoe]")

    current.append(PppoeInterface(name=interface, options=options))
    new_content = _rebuild_config(content, current)

    config_manager.write_config(new_content, backup=True)
    log.info("Added PPPoE interface %s", interface)

    return f"Added {interface} to [pppoe] section"


def remove_pppoe_interface(
    interface: str,
    config_path: Path | None = None,
) -> str:
    """Remove an interface from the ``[pppoe]`` section.

    Creates a backup before writing.

    Args:
        interface: Interface name to remove.
        config_path: Override the default configuration file path.

    Returns:
        A confirmation message string.

    Raises:
        ValueError: If the interface is not found in the section.
        FileNotFoundError: If the configuration file does not exist.
    """
    path = config_path or ACCEL_CONFIG
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    content = path.read_text(encoding="utf-8")
    current = _parse_pppoe_interfaces(content)

    # Find and remove
    new_list = [i for i in current if i.name != interface]
    if len(new_list) == len(current):
        raise ValueError(f"Interface {interface} not found in [pppoe]")

    new_content = _rebuild_config(content, new_list)

    config_manager.write_config(new_content, backup=True)
    log.info("Removed PPPoE interface %s", interface)

    return f"Removed {interface} from [pppoe] section"
