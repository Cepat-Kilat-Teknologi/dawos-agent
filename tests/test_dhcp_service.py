"""Tests for services/dhcp.py — DHCP server and relay."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import dhcp


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# dhcp_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dhcp_status_active():
    proc_active = _mock_proc("active")
    proc_leases = _mock_proc("")
    calls = [proc_active, proc_leases]

    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        side_effect=calls,
    ):
        result = await dhcp.dhcp_status()

    assert result["active"] is True
    assert result["service"] == "dnsmasq"


@pytest.mark.asyncio
async def test_dhcp_status_inactive():
    proc = _mock_proc("inactive", returncode=3)
    proc_leases = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        side_effect=[proc, proc_leases],
    ):
        result = await dhcp.dhcp_status()

    assert result["active"] is False


# ---------------------------------------------------------------------------
# dhcp_leases
# ---------------------------------------------------------------------------

LEASES = """\
1720000000 aa:bb:cc:dd:ee:ff 10.0.0.5 desktop-pc 01:aa:bb:cc:dd:ee:ff
1720000100 11:22:33:44:55:66 10.0.0.6 laptop *
"""


@pytest.mark.asyncio
async def test_dhcp_leases():
    proc = _mock_proc(LEASES)
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dhcp.dhcp_leases()

    assert result["count"] == 2
    assert result["leases"][0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert result["leases"][0]["ip"] == "10.0.0.5"
    assert result["leases"][1]["hostname"] == "laptop"


@pytest.mark.asyncio
async def test_dhcp_leases_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dhcp.dhcp_leases()

    assert result["count"] == 0


@pytest.mark.asyncio
async def test_dhcp_leases_empty():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dhcp.dhcp_leases()

    assert result["count"] == 0


# ---------------------------------------------------------------------------
# relay_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relay_status_active():
    proc_active = _mock_proc("active")
    proc_config = _mock_proc(
        "ExecStart={ path=/usr/sbin/dhcrelay ; "
        "argv[]=/usr/sbin/dhcrelay -i eth0 10.0.0.1 10.0.0.2 }"
    )

    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        side_effect=[proc_active, proc_config],
    ):
        result = await dhcp.relay_status()

    assert result["active"] is True
    assert result["config"]["interface"] == "eth0"
    assert "10.0.0.1" in result["config"]["servers"]


@pytest.mark.asyncio
async def test_relay_status_inactive():
    proc = _mock_proc("inactive", returncode=3)
    proc_config = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        side_effect=[proc, proc_config],
    ):
        result = await dhcp.relay_status()

    assert result["active"] is False


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dhcp_restart():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dhcp.dhcp_restart()

    assert result["success"] is True


@pytest.mark.asyncio
async def test_dhcp_restart_failure():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dhcp.dhcp_restart()

    assert result["success"] is False


@pytest.mark.asyncio
async def test_relay_restart():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dhcp.relay_restart()

    assert result["success"] is True


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.dhcp.asyncio.create_subprocess_shell",
        return_value=proc,
    ) as m:
        await dhcp._run("systemctl restart dnsmasq", sudo=True)
        cmd = m.call_args[0][0]
        assert cmd.startswith("sudo ")
