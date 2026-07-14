"""accel-ppp configuration file validator.

Parses an accel-ppp INI-style configuration string and returns
structured validation results.  Checks include:

* **Syntax** — valid section headers, no orphan keys before the first
  section, no malformed lines.
* **Required sections** — ``[modules]`` must be present.
* **Duplicate sections** — repeated section names produce warnings.
* **IP / CIDR validation** — values that look like IPv4 addresses or
  CIDR notation are verified with :mod:`ipaddress`.
* **Port range** — numeric port values must fall within 1–65535.
* **Empty values** — keys with a blank right-hand side of ``=``
  trigger informational notices.

The validator is intentionally lenient with accel-ppp quirks such as
bare module names in ``[modules]`` (lines without ``=``), IP-pool range
entries, and comma-separated RADIUS server specs.
"""

from __future__ import annotations

import ipaddress
import logging
import re

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(r"^\[([^\]]+)\]$")
_KEY_VALUE_RE = re.compile(r"^([a-zA-Z0-9_-]+)\s*=\s*(.*)$")
_IP_RE = re.compile(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$")
_CIDR_RE = re.compile(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2})$")
_PORT_RE = re.compile(r"^(\d+)$")

_REQUIRED_SECTIONS = {"modules"}

# Sections where bare keys (no ``=``) are expected and should not trigger
# warnings: ``[modules]`` lists module names, ``[ip-pool]`` lists ranges.
_BARE_KEY_SECTIONS = {"modules", "ip-pool"}

# Known keys that hold port numbers, used for range validation.
_PORT_KEYS = frozenset(
    {
        "tcp",
        "auth-port",
        "acct-port",
        "port",
        "cli-port",
    }
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_config(content: str) -> dict:
    """Validate an accel-ppp configuration string.

    Args:
        content: Raw configuration text (INI-style).

    Returns:
        A dict suitable for constructing
        :class:`~dawos_agent.models.schemas.ConfigValidationResponse`.
    """
    issues: list[dict] = []
    sections_found: list[str] = []
    section_counts: dict[str, int] = {}
    current_section = ""

    lines = content.splitlines()

    for lineno_0, raw_line in enumerate(lines):
        lineno = lineno_0 + 1
        line = raw_line.strip()

        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        # Section header
        sec_match = _SECTION_RE.match(line)
        if sec_match:
            current_section = sec_match.group(1)
            section_counts[current_section] = section_counts.get(current_section, 0) + 1
            if current_section not in sections_found:
                sections_found.append(current_section)
            continue

        # Lines before any section header
        if not current_section:
            issues.append(
                {
                    "severity": "error",
                    "line": lineno,
                    "section": "",
                    "message": (
                        f"Orphan line before any section header: " f"{_truncate(line)}"
                    ),
                }
            )
            continue

        # Key=value line
        kv_match = _KEY_VALUE_RE.match(line)
        if kv_match:
            key = kv_match.group(1)
            value = kv_match.group(2).strip()

            # Empty value info
            if not value:
                issues.append(
                    {
                        "severity": "info",
                        "line": lineno,
                        "section": current_section,
                        "message": f"Empty value for key '{key}'",
                    }
                )
                continue

            # Validate IPs in value
            _check_ip_values(value, lineno, current_section, key, issues)

            # Validate port numbers for known port keys
            _check_port_value(value, lineno, current_section, key, issues)
            continue

        # Bare key (no ``=``) — normal in [modules] and [ip-pool]
        if current_section not in _BARE_KEY_SECTIONS:
            # Could be an unrecognised syntax
            issues.append(
                {
                    "severity": "warning",
                    "line": lineno,
                    "section": current_section,
                    "message": (
                        f"Line has no '=' separator — possible syntax error: "
                        f"{_truncate(line)}"
                    ),
                }
            )

    # Post-parse checks
    _check_required_sections(sections_found, issues)
    _check_duplicate_sections(section_counts, issues)

    errors = sum(1 for i in issues if i["severity"] == "error")
    warnings = sum(1 for i in issues if i["severity"] == "warning")

    return {
        "valid": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "sections": sections_found,
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int = 60) -> str:
    """Truncate long lines for display in issue messages."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _check_ip_values(
    value: str,
    lineno: int,
    section: str,
    key: str,
    issues: list[dict],
) -> None:
    """Validate IPv4 addresses and CIDR notation in a value string."""
    # Check for CIDR first (e.g. gw=10.0.0.0/24)
    cidr_match = _CIDR_RE.match(value)
    if cidr_match:
        try:
            ipaddress.ip_network(cidr_match.group(1), strict=False)
        except ValueError:
            issues.append(
                {
                    "severity": "error",
                    "line": lineno,
                    "section": section,
                    "message": f"Invalid CIDR notation for '{key}': {value}",
                }
            )
        return

    # Check plain IP (e.g. server=10.0.0.1)
    ip_match = _IP_RE.match(value)
    if ip_match:
        try:
            ipaddress.ip_address(ip_match.group(1))
        except ValueError:
            issues.append(
                {
                    "severity": "error",
                    "line": lineno,
                    "section": section,
                    "message": f"Invalid IP address for '{key}': {value}",
                }
            )
        return

    # Check IPs embedded in comma-separated values (e.g. RADIUS server line)
    # server=10.0.0.1,secret,auth-port=1812
    if "," in value:
        parts = value.split(",")
        first = parts[0].strip()
        if _IP_RE.match(first):
            try:
                ipaddress.ip_address(first)
            except ValueError:
                issues.append(
                    {
                        "severity": "error",
                        "line": lineno,
                        "section": section,
                        "message": (f"Invalid IP address for '{key}': {first}"),
                    }
                )

    # Check IP:port pattern (e.g. tcp=127.0.0.1:2001)
    if ":" in value and "," not in value:
        host_part = value.split(":")[0]
        if _IP_RE.match(host_part):
            try:
                ipaddress.ip_address(host_part)
            except ValueError:
                issues.append(
                    {
                        "severity": "error",
                        "line": lineno,
                        "section": section,
                        "message": (f"Invalid IP address for '{key}': {host_part}"),
                    }
                )


def _check_port_value(
    value: str,
    lineno: int,
    section: str,
    key: str,
    issues: list[dict],
) -> None:
    """Validate port numbers for known port keys."""
    # Direct port key: port=2001
    if key in _PORT_KEYS:
        port_str = value
        # Handle ip:port format (e.g. tcp=127.0.0.1:2001)
        if ":" in value:
            port_str = value.rsplit(":", 1)[-1]
        if _PORT_RE.match(port_str):
            port = int(port_str)
            if port < 1 or port > 65535:
                issues.append(
                    {
                        "severity": "error",
                        "line": lineno,
                        "section": section,
                        "message": (
                            f"Port out of range (1-65535) for '{key}': " f"{port}"
                        ),
                    }
                )
        return

    # Check port sub-keys in comma-separated RADIUS lines
    # server=10.0.0.1,secret,auth-port=1812,acct-port=1813
    if "," in value:
        for part in value.split(","):
            sub = part.strip()
            if "=" in sub:
                sub_key, sub_val = sub.split("=", 1)
                sub_key = sub_key.strip()
                sub_val = sub_val.strip()
                if sub_key in _PORT_KEYS and _PORT_RE.match(sub_val):
                    port = int(sub_val)
                    if port < 1 or port > 65535:
                        issues.append(
                            {
                                "severity": "error",
                                "line": lineno,
                                "section": section,
                                "message": (
                                    f"Port out of range (1-65535) for "
                                    f"'{sub_key}': {port}"
                                ),
                            }
                        )


def _check_required_sections(
    sections: list[str],
    issues: list[dict],
) -> None:
    """Verify that all required sections are present."""
    for req in sorted(_REQUIRED_SECTIONS):
        if req not in sections:
            issues.append(
                {
                    "severity": "error",
                    "line": 0,
                    "section": "",
                    "message": f"Required section [{req}] is missing",
                }
            )


def _check_duplicate_sections(
    counts: dict[str, int],
    issues: list[dict],
) -> None:
    """Warn about duplicate section headers."""
    for name, count in sorted(counts.items()):
        if count > 1:
            issues.append(
                {
                    "severity": "warning",
                    "line": 0,
                    "section": name,
                    "message": (f"Section [{name}] appears {count} times"),
                }
            )
