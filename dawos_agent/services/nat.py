"""Per-customer NAT egress management — nftables ``@cust_egress`` map.

Mirrors the accel-cli ``nat`` module:

- ``set_egress`` / ``clear_egress`` — map a subscriber IP to a public IP
- ``add_public_ip`` / ``remove_public_ip`` — bind/unbind a public IP to the uplink
- ``nat_status`` — show egress map + postrouting rules + bound IPs
- ``box_egress`` — toggle the accelnat table on/off

The ``accelnat`` table (with ``@cust_egress`` map, ``postrouting`` chain
and SNAT rule) is auto-created when it does not already exist.

Persistence file: ``/etc/accel-nat-egress.nft`` (loaded by systemd on boot).
"""

from __future__ import annotations

import asyncio
import logging
import shlex

log = logging.getLogger(__name__)

PERSIST_FILE = "/etc/accel-nat-egress.nft"
TABLE_NAME = "accelnat"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(
    cmd: str, *, sudo: bool = False, stdin_data: str | None = None
) -> tuple[str, int]:
    """Execute a shell command asynchronously.

    Args:
        cmd: The command string to execute.
        sudo: If True, prefix the command with ``sudo``.

    Returns:
        A tuple of (stdout_text, return_code).
    """
    if sudo:
        cmd = f"sudo {cmd}"
    log.debug("exec: %s", cmd)
    proc = await asyncio.create_subprocess_exec(
        *shlex.split(cmd),
        stdin=asyncio.subprocess.PIPE if stdin_data else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(
        input=stdin_data.encode() if stdin_data else None
    )
    out = stdout.decode().strip()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        log.warning(
            "command failed (rc=%d): %s — %s",
            proc.returncode,
            cmd,
            err,
        )
    return out, proc.returncode


async def _run_ok(cmd: str, *, sudo: bool = False) -> str:
    """Execute a shell command, raising on failure.

    Args:
        cmd: The command string to execute.
        sudo: If True, prefix the command with ``sudo``.

    Returns:
        The stripped stdout text.

    Raises:
        RuntimeError: If the command exits with a non-zero return code.
    """
    out, rc = await _run(cmd, sudo=sudo)
    if rc != 0:
        raise RuntimeError(f"Command failed: {cmd} — {out}")
    return out


async def _ensure_egress_table() -> None:
    """Create the ``accelnat`` table structure if it does not exist.

    Creates the table, ``@cust_egress`` map, ``postrouting`` chain, and
    SNAT rule idempotently.  nftables ``add`` commands succeed silently
    when the object already exists, so this is safe to call on every
    write operation.
    """
    base_cmds = [
        f"nft add table ip {TABLE_NAME}",
        (
            f"nft add map ip {TABLE_NAME} cust_egress "
            "{ type ipv4_addr : ipv4_addr \\; }"
        ),
        (
            f"nft add chain ip {TABLE_NAME} postrouting "
            "{ type nat hook postrouting priority 100 \\; }"
        ),
    ]
    for cmd in base_cmds:
        _, rc = await _run(cmd, sudo=True)
        if rc != 0:
            raise RuntimeError(
                f"Cannot ensure nftables table '{TABLE_NAME}' — " f"failed at: {cmd}"
            )
    # ``nft add rule`` always appends — add the SNAT rule only when it is
    # not already present, otherwise the postrouting chain accumulates a
    # duplicate rule on every egress operation and grows unbounded (DA-H04).
    snat_rule = "snat to ip saddr map @cust_egress"
    existing, _ = await _run(f"nft list chain ip {TABLE_NAME} postrouting", sudo=True)
    if snat_rule not in existing:
        _, rc = await _run(
            f"nft add rule ip {TABLE_NAME} postrouting {snat_rule}", sudo=True
        )
        if rc != 0:
            raise RuntimeError(f"Cannot ensure nftables SNAT rule for '{TABLE_NAME}'")


# ---------------------------------------------------------------------------
# Egress map
# ---------------------------------------------------------------------------


async def get_egress_map() -> list[dict]:
    """Read the ``@cust_egress`` nftables map entries.

    Returns:
        A list of dicts with ``customer_ip`` and ``public_ip``
        for each active egress mapping.
    """
    out, rc = await _run(
        f"nft list map ip {TABLE_NAME} cust_egress",
        sudo=True,
    )
    if rc != 0:
        return []

    entries = []
    for line in out.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith(("table", "map", "type", "}")):
            # "10.0.0.5 : 1.2.3.4,"
            parts = line.replace(",", "").split(":")
            if len(parts) == 2:
                cip = parts[0].strip()
                pip = parts[1].strip()
                if cip and pip:
                    entries.append(
                        {
                            "customer_ip": cip,
                            "public_ip": pip,
                        }
                    )
    return entries


async def set_egress(customer_ip: str, public_ip: str) -> str:
    """Map a subscriber IP to a specific public egress IP.

    Auto-creates the ``accelnat`` table structure when it does not
    exist, then adds the mapping to ``@cust_egress`` and persists.

    Args:
        customer_ip: The subscriber's private IP address.
        public_ip: The public IP to use for egress NAT.

    Returns:
        A confirmation message string.
    """
    await _ensure_egress_table()
    await _run_ok(
        f"nft add element ip {TABLE_NAME} cust_egress "
        f"{{ {shlex.quote(customer_ip)} : {shlex.quote(public_ip)} }}",
        sudo=True,
    )
    await _persist()
    return f"Egress set: {customer_ip} → {public_ip}"


async def clear_egress(customer_ip: str) -> str:
    """Remove a subscriber's egress NAT mapping.

    Auto-creates the ``accelnat`` table structure when it does not
    exist (handles edge case where table was flushed externally).

    Args:
        customer_ip: The subscriber IP to unmap.

    Returns:
        A confirmation message string.
    """
    await _ensure_egress_table()
    await _run_ok(
        f"nft delete element ip {TABLE_NAME} cust_egress "
        f"{{ {shlex.quote(customer_ip)} }}",
        sudo=True,
    )
    await _persist()
    return f"Egress cleared for {customer_ip}"


# ---------------------------------------------------------------------------
# Public IP management
# ---------------------------------------------------------------------------


async def add_public_ip(
    public_ip: str,
    interface: str = "",
) -> str:
    """Bind a public IP address to the uplink interface.

    Args:
        public_ip: The public IP to add (as a /32).
        interface: Uplink interface name; auto-detected if empty.

    Returns:
        A confirmation message string.
    """
    if not interface:
        interface = await _detect_uplink()
    await _run_ok(
        f"ip addr add {shlex.quote(public_ip)}/32 dev {shlex.quote(interface)}",
        sudo=True,
    )
    return f"Added {public_ip} to {interface}"


async def remove_public_ip(
    public_ip: str,
    interface: str = "",
) -> str:
    """Remove a public IP address from the uplink interface.

    Args:
        public_ip: The public IP to remove.
        interface: Uplink interface name; auto-detected if empty.

    Returns:
        A confirmation message string.
    """
    if not interface:
        interface = await _detect_uplink()
    await _run_ok(
        f"ip addr del {shlex.quote(public_ip)}/32 dev {shlex.quote(interface)}",
        sudo=True,
    )
    return f"Removed {public_ip} from {interface}"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


async def nat_status() -> dict:
    """Return comprehensive NAT status.

    Includes the egress mapping table, postrouting rules, and all
    globally-scoped IP addresses bound on the host.

    Returns:
        A dictionary with ``egress_map``, ``postrouting_rules``,
        and ``bound_ips``.
    """
    egress = await get_egress_map()

    post_out, _ = await _run(
        f"nft list chain ip {TABLE_NAME} postrouting",
        sudo=True,
    )
    bound_out, _ = await _run(
        "ip -br addr show scope global",
        sudo=False,
    )

    return {
        "egress_map": egress,
        "postrouting_rules": post_out,
        "bound_ips": bound_out,
    }


# ---------------------------------------------------------------------------
# Box egress (toggle accelnat table)
# ---------------------------------------------------------------------------


async def box_egress_status() -> dict:
    """Check whether the per-customer egress NAT table is active.

    Returns:
        A dictionary with ``enabled`` (bool).
    """
    _, rc = await _run(
        f"nft list table ip {TABLE_NAME}",
        sudo=True,
    )
    return {"enabled": rc == 0}


async def box_egress_set(action: str) -> str:
    """Toggle the per-customer egress NAT table on or off.

    When enabled, creates the ``accelnat`` nftables table with a
    customer-to-public-IP SNAT map.  When disabled, removes the table.

    Args:
        action: ``"on"`` to enable or ``"off"`` to disable.

    Returns:
        A confirmation message string.

    Raises:
        ValueError: If *action* is not ``"on"`` or ``"off"``.
    """
    if action == "on":
        await _ensure_egress_table()
        await _persist()
        return "Box egress enabled"
    if action == "off":
        await _run(f"nft delete table ip {TABLE_NAME}", sudo=True)
        return "Box egress disabled"

    raise ValueError(f"Invalid action '{action}', use 'on' or 'off'")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def _persist() -> None:
    """Save the accelnat nftables table to the persistence file."""
    out, rc = await _run(
        f"nft list table ip {TABLE_NAME}",
        sudo=True,
    )
    if rc == 0 and out:
        content = f"#!/usr/sbin/nft -f\n# dawos-agent managed\n{out}\n"
        await _run(
            f"tee {PERSIST_FILE}",
            sudo=True,
            stdin_data=content,
        )


async def _detect_uplink() -> str:
    """Auto-detect the default gateway interface from the routing table.

    Returns:
        The interface name associated with the default route.

    Raises:
        RuntimeError: If no default route is found or cannot be parsed.
    """
    out, rc = await _run("ip route show default")
    if rc != 0 or not out:
        raise RuntimeError("Cannot detect uplink interface")
    # "default via 1.2.3.4 dev eth0 ..."
    parts = out.split()
    if "dev" in parts:
        idx = parts.index("dev")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    raise RuntimeError(f"Cannot parse default route: {out}")
