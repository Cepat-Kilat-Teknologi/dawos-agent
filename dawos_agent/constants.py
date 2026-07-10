"""Shared named constants used across multiple modules.

Centralises magic numbers that appear in more than one service or model
so that a single change propagates consistently.  Module-local constants
(used in only one file) remain in their respective modules.
"""

from __future__ import annotations

# -- Conntrack ---------------------------------------------------------------
CONNTRACK_RECOMMENDED_MIN: int = 262_144
"""Minimum ``nf_conntrack_max`` value recommended for BNG workloads."""

# -- Well-known ports --------------------------------------------------------
SNMPD_PORT: int = 161
"""Standard UDP port for the SNMP daemon."""

NODE_EXPORTER_PORT: int = 9100
"""Default Prometheus ``node_exporter`` HTTP port."""

# -- Shell-safety regex patterns ---------------------------------------------
# Canonical allow-lists for any value interpolated into a shell command.
# Applied both on request-body fields (``pattern=`` in schemas.py) and on
# path/query parameters (``Path``/``Query`` in routers) so that shell
# metacharacters are rejected with HTTP 422 before reaching a subprocess.
# Single source of truth: schemas.py imports these; do not redefine elsewhere.
RE_SAFE_NAME: str = r"^[a-zA-Z0-9._@-]+$"
"""Generic safe identifier: usernames, unit names, job/hook names."""

RE_SAFE_IFACE: str = r"^[a-zA-Z0-9._-]+$"
"""Network interface / VLAN name (e.g. ``eth0``, ``eth0.100``)."""

RE_SAFE_MAC: str = r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"
"""MAC address in colon-separated hex form."""

RE_SAFE_RATE: str = r"^[0-9]+[KMGkmg]?/[0-9]+[KMGkmg]?$"
"""Rate-limit string, e.g. ``5M/20M``."""

RE_SAFE_IP: str = r"^[0-9A-Fa-f.:/%]+$"
"""IPv4/IPv6 address or CIDR (loose; exact form validated downstream)."""

RE_SAFE_ROUTE_DST: str = r"^(default|[0-9A-Fa-f.:/%]+)$"
"""Route destination: ``default`` or an address/CIDR."""

RE_SAFE_DOMAIN: str = r"^[a-zA-Z0-9._-]+$"
"""DNS domain / hostname label."""

RE_SAFE_SYSCTL: str = r"^[a-z0-9_]+$"
"""Sysctl leaf key fragment."""

RE_SAFE_OPTIONS: str = r"^[a-zA-Z0-9._,=/ -]*$"
"""Free-form option string (may be empty)."""

RE_SAFE_ACCEL_CMD: str = r"^[a-zA-Z0-9 ._=:,/-]+$"
"""Whitelisted accel-cmd command string."""

RE_SAFE_ELEMENT: str = r"^[0-9A-Fa-f.:/-]+$"
"""nftables set element (IP/CIDR/range)."""

RE_SAFE_MATCH: str = r"^[A-Za-z0-9._:/%@-]+$"
"""accel-cmd match key (session SID / IP / username lookup); permits
IPv4/IPv6/CIDR and identifier characters while blocking every shell
metacharacter."""
