"""Tests for services/ntp.py — chronyc wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import ntp


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# ntp_status
# ---------------------------------------------------------------------------

CHRONY_TRACKING = """\
Reference ID    : D8EF2308 (ntp.ubuntu.com)
Stratum         : 2
Ref time (UTC)  : Sun Jul 06 10:00:00 2025
System time     : 0.000012345 seconds fast of NTP time
Last offset     : +0.000001234 seconds
RMS offset      : 0.000012000 seconds
Frequency       : 1.234 ppm slow
"""


@pytest.mark.asyncio
async def test_ntp_status():
    proc = _mock_proc(CHRONY_TRACKING)
    with patch(
        "dawos_agent.services.ntp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await ntp.ntp_status()

    assert result["synced"] is True
    assert result["stratum"] == 2
    assert "ntp.ubuntu.com" in result["reference"]


@pytest.mark.asyncio
async def test_ntp_status_not_synced():
    out = "Reference ID    : 00000000 ()\nStratum         : 0\n"
    proc = _mock_proc(out)
    with patch(
        "dawos_agent.services.ntp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await ntp.ntp_status()

    assert result["synced"] is False


@pytest.mark.asyncio
async def test_ntp_status_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.ntp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await ntp.ntp_status()

    assert result["synced"] is False


# ---------------------------------------------------------------------------
# ntp_sources
# ---------------------------------------------------------------------------

CHRONY_SOURCES = """\
MS Name/IP address       Stratum  Poll  Reach  LastRx  Last sample
===============================================================================
* ntp.ubuntu.com               2    6   377    42   +123us[ +456us] +/-   12ms
+ pool.ntp.org                 2    6   377    43   -234us[ -567us] +/-   15ms
"""


@pytest.mark.asyncio
async def test_ntp_sources():
    proc = _mock_proc(CHRONY_SOURCES)
    with patch(
        "dawos_agent.services.ntp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await ntp.ntp_sources()

    assert result["count"] == 2
    assert result["sources"][0]["name"] == "ntp.ubuntu.com"
    assert result["sources"][0]["tally"] == "*"
    assert result["sources"][1]["tally"] == "+"


@pytest.mark.asyncio
async def test_ntp_sources_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.ntp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await ntp.ntp_sources()

    assert result["count"] == 0
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_ntp_sources_empty():
    proc = _mock_proc("MS Name/IP address\n===\n")
    with patch(
        "dawos_agent.services.ntp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await ntp.ntp_sources()

    assert result["count"] == 0


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------


def test_safe_int():
    assert ntp._safe_int("42") == 42
    assert ntp._safe_int("abc") == 0


# ---------------------------------------------------------------------------
# _run sudo branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.ntp.asyncio.create_subprocess_shell",
        return_value=proc,
    ) as m:
        await ntp._run("chronyc tracking", sudo=True)
        cmd = m.call_args[0][0]
        assert cmd.startswith("sudo ")


# ---------------------------------------------------------------------------
# ntp_status synchronized text detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ntp_status_synchronized_text():
    """Cover the 'synchronized' keyword detection branch."""
    out = (
        "Reference ID    : D8EF2308 (ntp.ubuntu.com)\n"
        "Stratum         : 0\n"
        "Leap status     : synchronized\n"
    )
    proc = _mock_proc(out)
    with patch(
        "dawos_agent.services.ntp.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await ntp.ntp_status()

    assert result["synced"] is True
