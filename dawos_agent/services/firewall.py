"""Firewall & NAT management — nftables wrapper + sysctl controls.

Provides high-level operations for a PPPoE BNG node:
- Enable/disable IP forwarding (sysctl)
- NAT masquerade for subscriber traffic
- View nftables ruleset
- Dry-run validation via ``nft -c`` before apply

All mutating operations use ``sudo``.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile

from ..models.schemas import FirewallStatus, SysctlStatus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(cmd: str, *, sudo: bool = False) -> tuple[str, int]:
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
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    out = stdout.decode().strip()
    if proc.returncode != 0:
        err = stderr.decode().strip()
        log.warning("command failed (rc=%d): %s — %s", proc.returncode, cmd, err)
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


# ---------------------------------------------------------------------------
# sysctl — IP forwarding
# ---------------------------------------------------------------------------


async def get_sysctl() -> SysctlStatus:
    """Read the current IPv4 and IPv6 forwarding sysctl values.

    Returns:
        A :class:`SysctlStatus` with ``ip_forward`` and ``ip6_forward``.
    """
    ipv4_out, _ = await _run("sysctl -n net.ipv4.ip_forward")
    ipv6_out, _ = await _run("sysctl -n net.ipv6.conf.all.forwarding")

    return SysctlStatus(
        ip_forward=ipv4_out.strip() == "1",
        ip6_forward=ipv6_out.strip() == "1",
    )


async def set_sysctl(
    *, ip_forward: bool = True, ip6_forward: bool = False
) -> SysctlStatus:
    """Set IPv4/IPv6 forwarding sysctl values and persist to sysctl.d.

    Args:
        ip_forward: Enable IPv4 forwarding (default True).
        ip6_forward: Enable IPv6 forwarding (default False).

    Returns:
        The updated :class:`SysctlStatus`.
    """
    v4 = "1" if ip_forward else "0"
    v6 = "1" if ip6_forward else "0"

    await _run_ok(f"sysctl -w net.ipv4.ip_forward={v4}", sudo=True)
    await _run_ok(f"sysctl -w net.ipv6.conf.all.forwarding={v6}", sudo=True)

    # Persist
    conf = (
        f"# dawos-agent managed\n"
        f"net.ipv4.ip_forward = {v4}\n"
        f"net.ipv6.conf.all.forwarding = {v6}\n"
    )
    await _run(f"tee /etc/sysctl.d/90-dawos.conf <<< '{conf}'", sudo=True)

    return SysctlStatus(ip_forward=ip_forward, ip6_forward=ip6_forward)


# ---------------------------------------------------------------------------
# nftables — ruleset management
# ---------------------------------------------------------------------------


async def get_firewall_status() -> FirewallStatus:
    """Return comprehensive firewall status.

    Checks whether nftables is active, counts rules, detects NAT
    masquerade presence, and includes current sysctl forwarding state.

    Returns:
        A :class:`FirewallStatus` with ``enabled``, ``backend``,
        ``rules_count``, ``nat_enabled``, and ``sysctl``.
    """
    # Check if nftables service is active
    _, rc = await _run("systemctl is-active nftables")
    enabled = rc == 0

    # Count rules
    rules_count = 0
    nat_enabled = False
    if enabled:
        out, rc2 = await _run("nft list ruleset", sudo=True)
        if rc2 == 0:
            rules_count = out.count("\n") + 1 if out else 0
            nat_enabled = "masquerade" in out

    sysctl = await get_sysctl()

    return FirewallStatus(
        enabled=enabled,
        backend="nftables",
        rules_count=rules_count,
        nat_enabled=nat_enabled,
        sysctl=sysctl,
    )


async def list_ruleset() -> tuple[str, int]:
    """Return the full nftables ruleset as text.

    Returns:
        A tuple of (ruleset_text, rule_count).

    Raises:
        RuntimeError: If ``nft list ruleset`` fails.
    """
    out, rc = await _run("nft list ruleset", sudo=True)
    if rc != 0:
        raise RuntimeError(f"Failed to list ruleset: {out}")
    rules_count = out.count("\n") + 1 if out else 0
    return out, rules_count


async def setup_masquerade(wan_interface: str) -> str:
    """Enable NAT masquerade on the WAN interface.

    Creates the ``dawos-nat`` nftables table with a postrouting
    masquerade rule for subscriber traffic.  Idempotent — flushes
    any existing ``dawos-nat`` table before recreating.

    Also ensures IPv4 forwarding is enabled via sysctl.

    Args:
        wan_interface: The WAN-facing interface name (e.g. ``eth0``).

    Returns:
        A confirmation message string.
    """
    # Remove existing dawos nat table if present (idempotent)
    await _run("nft delete table ip dawos-nat", sudo=True)

    # Create table + chain + masquerade rule
    commands = [
        "nft add table ip dawos-nat",
        "nft add chain ip dawos-nat postrouting { type nat hook postrouting priority 100 \\; }",
        f'nft add rule ip dawos-nat postrouting oifname "{wan_interface}" masquerade',
    ]

    for cmd in commands:
        await _run_ok(cmd, sudo=True)

    # Ensure IP forwarding is enabled
    await set_sysctl(ip_forward=True)

    return f"NAT masquerade enabled on {wan_interface}"


async def remove_masquerade() -> str:
    """Remove the dawos NAT masquerade nftables table.

    Returns:
        A confirmation message string.

    Raises:
        RuntimeError: If the table deletion fails.
    """
    await _run_ok("nft delete table ip dawos-nat", sudo=True)
    return "NAT masquerade removed"


async def save_ruleset() -> str:
    """Persist the current nftables ruleset to ``/etc/nftables.conf``.

    Returns:
        A confirmation message string.

    Raises:
        RuntimeError: If reading or writing the ruleset fails.
    """
    out, rc = await _run("nft list ruleset", sudo=True)
    if rc != 0:
        raise RuntimeError(f"Failed to list ruleset: {out}")

    # Write to config file
    conf_content = (
        f"#!/usr/sbin/nft -f\n"
        f"# dawos-agent managed — saved ruleset\n"
        f"flush ruleset\n\n{out}\n"
    )
    await _run_ok(
        f"tee /etc/nftables.conf > /dev/null << 'DAWOS_EOF'\n{conf_content}\nDAWOS_EOF",
        sudo=True,
    )

    return "Ruleset saved to /etc/nftables.conf"


# ---------------------------------------------------------------------------
# Dry-run validation — nft -c
# ---------------------------------------------------------------------------


async def validate_ruleset(ruleset_text: str) -> dict:
    """Validate an nftables ruleset without applying it.

    Writes *ruleset_text* to a temporary file and runs ``nft -c -f``
    (check mode) to catch syntax errors before they affect the live
    firewall.

    Args:
        ruleset_text: The nftables ruleset content to validate.

    Returns:
        A dictionary with ``valid`` (bool) and ``detail`` (message).
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".nft",
        prefix="dawos-validate-",
        delete=False,
    ) as tmp:
        tmp.write(ruleset_text)
        tmp_path = tmp.name

    out, rc = await _run(f"nft -c -f {tmp_path}", sudo=True)

    # Clean up temp file
    # pylint: disable=import-outside-toplevel
    import contextlib
    import os

    with contextlib.suppress(OSError):
        os.unlink(tmp_path)

    if rc == 0:
        return {"valid": True, "detail": "Ruleset syntax OK"}
    return {"valid": False, "detail": out or "Syntax validation failed"}
