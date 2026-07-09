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
