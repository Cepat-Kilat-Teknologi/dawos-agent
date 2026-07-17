"""Tests for services/flow_accounting.py — NetFlow/sFlow/IPFIX."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import flow_accounting


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# flow_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_status_pmacctd():
    proc = _mock_proc("active")
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await flow_accounting.flow_status()

    assert result["active"] is True
    assert result["daemon"] == "pmacctd"


@pytest.mark.asyncio
async def test_flow_status_softflowd():
    proc_inactive = _mock_proc("inactive", returncode=3)
    proc_active = _mock_proc("active")
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc_inactive, proc_active],
    ):
        result = await flow_accounting.flow_status()

    assert result["active"] is True
    assert result["daemon"] == "softflowd"


@pytest.mark.asyncio
async def test_flow_status_none():
    proc1 = _mock_proc("inactive", returncode=3)
    proc2 = _mock_proc("inactive", returncode=3)
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc1, proc2],
    ):
        result = await flow_accounting.flow_status()

    assert result["active"] is False
    assert result["daemon"] == "none"


# ---------------------------------------------------------------------------
# flow_collectors
# ---------------------------------------------------------------------------

SOFTFLOWD_CFG = """\
# softflowd defaults
INTERFACE=eth0
COLLECTOR='10.0.0.100:9996'
OPTIONS="-v 9"
"""

PMACCTD_CFG = """\
daemonize: true
nfacctd_ip: 10.0.0.200
nfacctd_port: 9995
"""


@pytest.mark.asyncio
async def test_flow_collectors_softflowd():
    proc_sf = _mock_proc(SOFTFLOWD_CFG)
    proc_pm = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc_sf, proc_pm],
    ):
        result = await flow_accounting.flow_collectors()

    assert result["count"] == 1
    assert result["collectors"][0]["host"] == "10.0.0.100"
    assert result["collectors"][0]["port"] == 9996
    assert result["collectors"][0]["source"] == "softflowd"


@pytest.mark.asyncio
async def test_flow_collectors_pmacctd():
    proc_sf = _mock_proc("", returncode=1)
    proc_pm = _mock_proc(PMACCTD_CFG)
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc_sf, proc_pm],
    ):
        result = await flow_accounting.flow_collectors()

    assert result["count"] == 1
    assert result["collectors"][0]["host"] == "10.0.0.200"
    assert result["collectors"][0]["port"] == 9995
    assert result["collectors"][0]["source"] == "pmacctd"


@pytest.mark.asyncio
async def test_flow_collectors_none():
    proc1 = _mock_proc("", returncode=1)
    proc2 = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc1, proc2],
    ):
        result = await flow_accounting.flow_collectors()

    assert result["count"] == 0


@pytest.mark.asyncio
async def test_flow_collectors_softflowd_no_port():
    """Collector without port should default to 9995."""
    cfg = "COLLECTOR='10.0.0.50'\n"
    proc_sf = _mock_proc(cfg)
    proc_pm = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc_sf, proc_pm],
    ):
        result = await flow_accounting.flow_collectors()

    assert result["count"] == 1
    assert result["collectors"][0]["port"] == 9995


# ---------------------------------------------------------------------------
# flow_stats
# ---------------------------------------------------------------------------

STATS_OUTPUT = """\
softflowd v0.9.9 started
Flows exported: 1234
Packets processed: 56789
"""


@pytest.mark.asyncio
async def test_flow_stats():
    proc = _mock_proc(STATS_OUTPUT)
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await flow_accounting.flow_stats()

    assert result["flows_exported"] == 1234
    assert result["packets_processed"] == 56789


@pytest.mark.asyncio
async def test_flow_stats_fallback():
    """First command fails, second works."""
    proc_fail = _mock_proc("", returncode=1)
    proc_ok = _mock_proc("Flows exported: 10\nPackets processed: 20")
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc_fail, proc_ok],
    ):
        result = await flow_accounting.flow_stats()

    assert result["flows_exported"] == 10
    assert result["packets_processed"] == 20


@pytest.mark.asyncio
async def test_flow_stats_empty():
    proc = _mock_proc("no stats")
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await flow_accounting.flow_stats()

    assert result["flows_exported"] == 0
    assert result["packets_processed"] == 0


# ---------------------------------------------------------------------------
# flow_restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flow_restart_active_daemon():
    """Restart a detected active daemon."""
    proc_status = _mock_proc("active")  # pmacctd active
    proc_restart = _mock_proc("")
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc_status, proc_restart],
    ):
        result = await flow_accounting.flow_restart()

    assert result["success"] is True
    assert result["daemon"] == "pmacctd"


@pytest.mark.asyncio
async def test_flow_restart_no_daemon():
    """No daemon active — fallback to softflowd."""
    proc1 = _mock_proc("inactive", returncode=3)
    proc2 = _mock_proc("inactive", returncode=3)
    proc_restart = _mock_proc("")
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc1, proc2, proc_restart],
    ):
        result = await flow_accounting.flow_restart()

    assert result["success"] is True
    assert result["daemon"] == "softflowd"


@pytest.mark.asyncio
async def test_flow_restart_failure():
    proc_status = _mock_proc("active")  # pmacctd
    proc_restart = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        side_effect=[proc_status, proc_restart],
    ):
        result = await flow_accounting.flow_restart()

    assert result["success"] is False


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.flow_accounting.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        await flow_accounting._run("systemctl restart softflowd", sudo=True)
        cmd = " ".join(m.call_args[0])
        assert cmd.startswith("sudo ")
