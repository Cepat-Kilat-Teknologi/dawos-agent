"""Tests for services/vrrp.py — VRRP/HA keepalived."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import vrrp


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# vrrp_status
# ---------------------------------------------------------------------------

KEEPALIVED_STATS = """\
VRRP Instance: WAN_VIP
  State: MASTER
  Priority: 100
  Virtual IP: 203.0.113.1
VRRP Instance: LAN_VIP
  State: BACKUP
  Priority: 90
  Virtual IP: 10.0.0.1
"""


@pytest.mark.asyncio
async def test_vrrp_status_active():
    proc_active = _mock_proc("active")
    proc_stats = _mock_proc(KEEPALIVED_STATS)
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        side_effect=[proc_active, proc_stats],
    ):
        result = await vrrp.vrrp_status()

    assert result["active"] is True
    assert len(result["groups"]) == 2
    assert result["groups"][0]["name"] == "WAN_VIP"
    assert result["groups"][0]["state"] == "MASTER"
    assert result["groups"][0]["priority"] == 100
    assert result["groups"][0]["vip"] == "203.0.113.1"
    assert result["groups"][1]["name"] == "LAN_VIP"
    assert result["groups"][1]["state"] == "BACKUP"


@pytest.mark.asyncio
async def test_vrrp_status_inactive():
    proc = _mock_proc("inactive", returncode=3)
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await vrrp.vrrp_status()

    assert result["active"] is False
    assert result["groups"] == []


@pytest.mark.asyncio
async def test_vrrp_status_active_no_stats():
    proc_active = _mock_proc("active")
    proc_stats = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        side_effect=[proc_active, proc_stats],
    ):
        result = await vrrp.vrrp_status()

    assert result["active"] is True
    assert result["groups"] == []


# ---------------------------------------------------------------------------
# vrrp_group_detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vrrp_group_detail_found():
    proc_active = _mock_proc("active")
    proc_stats = _mock_proc(KEEPALIVED_STATS)
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        side_effect=[proc_active, proc_stats],
    ):
        result = await vrrp.vrrp_group_detail("WAN_VIP")

    assert result["found"] is True
    assert result["group"]["name"] == "WAN_VIP"


@pytest.mark.asyncio
async def test_vrrp_group_detail_not_found():
    proc = _mock_proc("inactive", returncode=3)
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await vrrp.vrrp_group_detail("NONEXISTENT")

    assert result["found"] is False


# ---------------------------------------------------------------------------
# vrrp_failover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vrrp_failover():
    proc = _mock_proc("Failover signal sent for WAN_VIP")
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await vrrp.vrrp_failover("WAN_VIP")

    assert result["success"] is True
    assert result["group"] == "WAN_VIP"


@pytest.mark.asyncio
async def test_vrrp_failover_failure():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await vrrp.vrrp_failover("NONE")

    assert result["success"] is False


# ---------------------------------------------------------------------------
# vrrp_restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vrrp_restart():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await vrrp.vrrp_restart()

    assert result["success"] is True


@pytest.mark.asyncio
async def test_vrrp_restart_failure():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await vrrp.vrrp_restart()

    assert result["success"] is False


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.vrrp.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        await vrrp._run("systemctl restart keepalived", sudo=True)
        cmd = " ".join(m.call_args[0])
        assert cmd.startswith("sudo ")
