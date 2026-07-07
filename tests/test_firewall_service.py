"""Tests for services/firewall.py — mocked subprocess."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import firewall

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


SAMPLE_RULESET = """\
table ip dawos-nat {
    chain postrouting {
        type nat hook postrouting priority 100; policy accept;
        oifname "eth0" masquerade
    }
}
table ip filter {
    chain input {
        type filter hook input priority 0; policy accept;
    }
}"""


# ---------------------------------------------------------------------------
# sysctl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sysctl():
    call_count = 0

    async def mock_shell(cmd, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _mock_proc("1")  # ipv4
        return _mock_proc("0")  # ipv6

    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        side_effect=mock_shell,
    ):
        result = await firewall.get_sysctl()

    assert result.ip_forward is True
    assert result.ip6_forward is False


@pytest.mark.asyncio
async def test_get_sysctl_disabled():
    proc = _mock_proc("0")
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await firewall.get_sysctl()

    assert result.ip_forward is False
    assert result.ip6_forward is False


@pytest.mark.asyncio
async def test_set_sysctl():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await firewall.set_sysctl(ip_forward=True, ip6_forward=True)

    assert result.ip_forward is True
    assert result.ip6_forward is True


@pytest.mark.asyncio
async def test_set_sysctl_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Command failed"):
        await firewall.set_sysctl(ip_forward=True)


# ---------------------------------------------------------------------------
# Firewall status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_firewall_status_enabled():
    call_count = 0

    async def mock_shell(cmd, **kw):
        nonlocal call_count
        call_count += 1
        if "is-active" in cmd:
            return _mock_proc("active")
        if "nft list" in cmd:
            return _mock_proc(SAMPLE_RULESET)
        if "ip_forward" in cmd:
            return _mock_proc("1")
        return _mock_proc("0")

    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        side_effect=mock_shell,
    ):
        status = await firewall.get_firewall_status()

    assert status.enabled is True
    assert status.nat_enabled is True
    assert status.rules_count > 0
    assert status.sysctl is not None
    assert status.backend == "nftables"


@pytest.mark.asyncio
async def test_get_firewall_status_disabled():
    call_count = 0

    async def mock_shell(cmd, **kw):
        nonlocal call_count
        call_count += 1
        if "is-active" in cmd:
            return _mock_proc("inactive", returncode=3)
        # sysctl calls
        return _mock_proc("0")

    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        side_effect=mock_shell,
    ):
        status = await firewall.get_firewall_status()

    assert status.enabled is False
    assert status.nat_enabled is False
    assert status.rules_count == 0


# ---------------------------------------------------------------------------
# Ruleset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_ruleset():
    proc = _mock_proc(SAMPLE_RULESET)
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        raw, count = await firewall.list_ruleset()

    assert "dawos-nat" in raw
    assert "masquerade" in raw
    assert count > 0


@pytest.mark.asyncio
async def test_list_ruleset_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Failed to list"):
        await firewall.list_ruleset()


# ---------------------------------------------------------------------------
# NAT masquerade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_masquerade():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await firewall.setup_masquerade("eth0")

    assert "masquerade enabled" in msg
    assert "eth0" in msg


@pytest.mark.asyncio
async def test_setup_masquerade_error():
    call_count = 0

    async def mock_shell(cmd, **kw):
        nonlocal call_count
        call_count += 1
        # First call (delete old table) succeeds or fails silently
        if call_count == 1:
            return _mock_proc("", returncode=1)  # no existing table — ok
        # Second call (add table) fails
        if call_count == 2:
            return _mock_proc("error", returncode=1)
        return _mock_proc("")

    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        side_effect=mock_shell,
    ), pytest.raises(RuntimeError):
        await firewall.setup_masquerade("eth0")


@pytest.mark.asyncio
async def test_remove_masquerade():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await firewall.remove_masquerade()

    assert "removed" in msg


@pytest.mark.asyncio
async def test_remove_masquerade_error():
    proc = _mock_proc("no such table", returncode=1)
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError):
        await firewall.remove_masquerade()


# ---------------------------------------------------------------------------
# Save ruleset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_ruleset():
    call_count = 0

    async def mock_shell(cmd, **kw):
        nonlocal call_count
        call_count += 1
        if "nft list" in cmd:
            return _mock_proc(SAMPLE_RULESET)
        return _mock_proc("")  # tee

    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        side_effect=mock_shell,
    ):
        msg = await firewall.save_ruleset()

    assert "saved" in msg.lower()


@pytest.mark.asyncio
async def test_save_ruleset_list_fails():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Failed to list"):
        await firewall.save_ruleset()


# ---------------------------------------------------------------------------
# _run helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ) as m:
        await firewall._run("nft list ruleset", sudo=True)
        cmd = m.call_args[0][0]
        assert cmd.startswith("sudo ")


@pytest.mark.asyncio
async def test_run_ok_raises():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Command failed"):
        await firewall._run_ok("nft list ruleset")


# ---------------------------------------------------------------------------
# nft dry-run validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_ruleset_valid():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await firewall.validate_ruleset("table ip test { chain c { } }")

    assert result["valid"] is True
    assert "OK" in result["detail"]


@pytest.mark.asyncio
async def test_validate_ruleset_invalid():
    proc = _mock_proc("Error: syntax error", returncode=1)
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await firewall.validate_ruleset("bad { syntax")

    assert result["valid"] is False
    assert "syntax error" in result["detail"]


@pytest.mark.asyncio
async def test_validate_ruleset_empty_error():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await firewall.validate_ruleset("")

    assert result["valid"] is False
    assert "failed" in result["detail"].lower()


@pytest.mark.asyncio
async def test_validate_ruleset_unlink_oserror():
    """Cover the OSError handler when temp file cleanup fails."""
    proc = _mock_proc("")
    with (
        patch(
            "dawos_agent.services.firewall.asyncio.create_subprocess_shell",
            return_value=proc,
        ),
        patch("os.unlink", side_effect=OSError("permission denied")),
    ):
        result = await firewall.validate_ruleset("table ip test { }")

    # Should still succeed despite cleanup failure
    assert result["valid"] is True
