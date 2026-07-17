"""Tests for services/nat.py — per-customer egress NAT."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import nat

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# get_egress_map
# ---------------------------------------------------------------------------

EGRESS_MAP_OUTPUT = """\
table ip accelnat {
    map cust_egress {
        type ipv4_addr : ipv4_addr
        elements = {
                10.0.0.2 : 1.2.3.4,
                10.0.0.3 : 1.2.3.5
        }
    }
}
"""


@pytest.mark.asyncio
async def test_get_egress_map():
    proc = _mock_proc(EGRESS_MAP_OUTPUT)
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await nat.get_egress_map()

    assert len(result) == 2
    assert result[0]["customer_ip"] == "10.0.0.2"
    assert result[0]["public_ip"] == "1.2.3.4"


@pytest.mark.asyncio
async def test_get_egress_map_empty():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await nat.get_egress_map()

    assert result == []


# ---------------------------------------------------------------------------
# set_egress / clear_egress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_egress():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        msg = await nat.set_egress("10.0.0.2", "1.2.3.4")

    assert "10.0.0.2" in msg
    assert "1.2.3.4" in msg


@pytest.mark.asyncio
async def test_set_egress_error():
    proc = _mock_proc("error", returncode=1)
    with (
        patch(
            "dawos_agent.services.nat.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError),
    ):
        await nat.set_egress("10.0.0.2", "1.2.3.4")


@pytest.mark.asyncio
async def test_set_egress_snat_rule_not_duplicated():
    """An already-present SNAT rule is not re-added on each call (DA-H04)."""
    added = 0

    async def mock_shell(*args, **kw):
        cmd = " ".join(args)
        nonlocal added
        if "list chain" in cmd:
            return _mock_proc("snat to ip saddr map @cust_egress")
        if "add rule" in cmd:
            added += 1
        return _mock_proc("")

    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        side_effect=mock_shell,
    ):
        await nat.set_egress("10.0.0.2", "1.2.3.4")

    assert added == 0


@pytest.mark.asyncio
async def test_ensure_egress_snat_rule_failure():
    """A failure adding the SNAT rule must raise (DA-H04)."""

    async def mock_shell(*args, **kw):
        cmd = " ".join(args)
        if "list chain" in cmd:
            return _mock_proc("")  # rule absent → attempt add
        if "add rule" in cmd:
            return _mock_proc("err", returncode=1)  # add fails
        return _mock_proc("")

    with (
        patch(
            "dawos_agent.services.nat.asyncio.create_subprocess_exec",
            side_effect=mock_shell,
        ),
        pytest.raises(RuntimeError, match="SNAT rule"),
    ):
        await nat.set_egress("10.0.0.2", "1.2.3.4")


@pytest.mark.asyncio
async def test_clear_egress():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        msg = await nat.clear_egress("10.0.0.2")

    assert "10.0.0.2" in msg


@pytest.mark.asyncio
async def test_clear_egress_error():
    proc = _mock_proc("error", returncode=1)
    with (
        patch(
            "dawos_agent.services.nat.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError),
    ):
        await nat.clear_egress("10.0.0.2")


# ---------------------------------------------------------------------------
# Public IP management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_public_ip_with_interface():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        msg = await nat.add_public_ip("1.2.3.4", "eth0")

    assert "1.2.3.4" in msg
    assert "eth0" in msg


@pytest.mark.asyncio
async def test_add_public_ip_auto_detect():
    call_count = 0

    async def mock_shell(*args, **kw):
        cmd = " ".join(args)
        nonlocal call_count
        call_count += 1
        if "ip route show default" in cmd:
            return _mock_proc("default via 1.2.3.1 dev eth0")
        return _mock_proc("")

    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        side_effect=mock_shell,
    ):
        msg = await nat.add_public_ip("1.2.3.4")

    assert "1.2.3.4" in msg


@pytest.mark.asyncio
async def test_add_public_ip_error():
    call_count = 0

    async def mock_shell(*args, **kw):
        cmd = " ".join(args)
        nonlocal call_count
        call_count += 1
        if "ip route show default" in cmd:
            return _mock_proc("default via 1.2.3.1 dev eth0")
        return _mock_proc("error", returncode=1)

    with (
        patch(
            "dawos_agent.services.nat.asyncio.create_subprocess_exec",
            side_effect=mock_shell,
        ),
        pytest.raises(RuntimeError),
    ):
        await nat.add_public_ip("1.2.3.4")


@pytest.mark.asyncio
async def test_remove_public_ip():
    call_count = 0

    async def mock_shell(*args, **kw):
        cmd = " ".join(args)
        nonlocal call_count
        call_count += 1
        if "ip route show default" in cmd:
            return _mock_proc("default via 1.2.3.1 dev eth0")
        return _mock_proc("")

    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        side_effect=mock_shell,
    ):
        msg = await nat.remove_public_ip("1.2.3.4")

    assert "1.2.3.4" in msg


@pytest.mark.asyncio
async def test_remove_public_ip_error():
    call_count = 0

    async def mock_shell(*args, **kw):
        cmd = " ".join(args)
        nonlocal call_count
        call_count += 1
        if "ip route show default" in cmd:
            return _mock_proc("default via 1.2.3.1 dev eth0")
        return _mock_proc("error", returncode=1)

    with (
        patch(
            "dawos_agent.services.nat.asyncio.create_subprocess_exec",
            side_effect=mock_shell,
        ),
        pytest.raises(RuntimeError),
    ):
        await nat.remove_public_ip("1.2.3.4")


# ---------------------------------------------------------------------------
# nat_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nat_status():
    async def mock_shell(*args, **kw):
        cmd = " ".join(args)
        if "cust_egress" in cmd:
            return _mock_proc(EGRESS_MAP_OUTPUT)
        if "postrouting" in cmd:
            return _mock_proc("snat to ip saddr map @cust_egress")
        return _mock_proc("eth0  UP  1.2.3.4/32")

    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        side_effect=mock_shell,
    ):
        result = await nat.nat_status()

    assert len(result["egress_map"]) == 2
    assert "snat" in result["postrouting_rules"]


# ---------------------------------------------------------------------------
# box_egress
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_box_egress_status_enabled():
    proc = _mock_proc("table ip accelnat { }")
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await nat.box_egress_status()

    assert result["enabled"] is True


@pytest.mark.asyncio
async def test_box_egress_status_disabled():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await nat.box_egress_status()

    assert result["enabled"] is False


@pytest.mark.asyncio
async def test_box_egress_set_on():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        msg = await nat.box_egress_set("on")

    assert "enabled" in msg.lower()


@pytest.mark.asyncio
async def test_box_egress_set_off():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        msg = await nat.box_egress_set("off")

    assert "disabled" in msg.lower()


@pytest.mark.asyncio
async def test_box_egress_set_invalid():
    with pytest.raises(ValueError, match="Invalid action"):
        await nat.box_egress_set("maybe")


# ---------------------------------------------------------------------------
# _detect_uplink
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_uplink():
    proc = _mock_proc("default via 1.2.3.1 dev eth0 proto static")
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await nat._detect_uplink()

    assert result == "eth0"


@pytest.mark.asyncio
async def test_detect_uplink_no_default():
    proc = _mock_proc("", returncode=1)
    with (
        patch(
            "dawos_agent.services.nat.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="Cannot detect"),
    ):
        await nat._detect_uplink()


@pytest.mark.asyncio
async def test_detect_uplink_no_dev():
    proc = _mock_proc("default via 1.2.3.1")
    with (
        patch(
            "dawos_agent.services.nat.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="Cannot parse"),
    ):
        await nat._detect_uplink()


# ---------------------------------------------------------------------------
# _persist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_success():
    async def mock_shell(*args, **kw):
        cmd = " ".join(args)
        if "nft list" in cmd:
            return _mock_proc("table ip accelnat { }")
        return _mock_proc("")  # tee

    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        side_effect=mock_shell,
    ):
        await nat._persist()  # should not raise


@pytest.mark.asyncio
async def test_persist_no_table():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        await nat._persist()  # should not raise (silent fail)


# ---------------------------------------------------------------------------
# _run helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.nat.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        await nat._run("nft list table", sudo=True)
        cmd = " ".join(m.call_args[0])
        assert cmd.startswith("sudo ")


@pytest.mark.asyncio
async def test_run_ok_raises():
    proc = _mock_proc("error", returncode=1)
    with (
        patch(
            "dawos_agent.services.nat.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="Command failed"),
    ):
        await nat._run_ok("nft add element")
