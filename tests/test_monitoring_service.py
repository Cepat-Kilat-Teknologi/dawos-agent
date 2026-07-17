"""Tests for services/monitoring.py — Prometheus/SNMP export."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import monitoring


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# monitoring_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitoring_status_both_active():
    proc = _mock_proc("active")
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.monitoring_status()

    assert result["count"] == 2
    assert result["exporters"][0]["service"] == "node_exporter"
    assert result["exporters"][0]["active"] is True
    assert result["exporters"][1]["service"] == "snmpd"


@pytest.mark.asyncio
async def test_monitoring_status_inactive():
    proc = _mock_proc("inactive", returncode=3)
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.monitoring_status()

    assert result["exporters"][0]["active"] is False


# ---------------------------------------------------------------------------
# exporter_metrics — node_exporter
# ---------------------------------------------------------------------------

METRICS_OUTPUT = """\
# HELP node_cpu_seconds_total Total CPU time
# TYPE node_cpu_seconds_total counter
node_cpu_seconds_total{cpu="0",mode="idle"} 12345.67
node_memory_MemTotal_bytes 8589934592
"""


@pytest.mark.asyncio
async def test_exporter_metrics_node_exporter():
    proc = _mock_proc(METRICS_OUTPUT)
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.exporter_metrics("node_exporter")

    assert result["available"] is True
    assert result["service"] == "node_exporter"
    assert len(result["metrics"]) >= 2
    assert result["metrics"][0]["name"] == "node_cpu_seconds_total"


@pytest.mark.asyncio
async def test_exporter_metrics_node_exporter_unavailable():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.exporter_metrics("node_exporter")

    assert result["available"] is False


# ---------------------------------------------------------------------------
# exporter_metrics — snmpd
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exporter_metrics_snmpd():
    proc = _mock_proc("udp  UNCONN  0  0  0.0.0.0:161")
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.exporter_metrics("snmpd")

    assert result["available"] is True
    assert result["service"] == "snmpd"


@pytest.mark.asyncio
async def test_exporter_metrics_snmpd_unavailable():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.exporter_metrics("snmpd")

    assert result["available"] is False


# ---------------------------------------------------------------------------
# configure_exporter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_exporter_enable():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.configure_exporter("node_exporter", enable=True)

    assert result["success"] is True
    assert result["enabled"] is True


@pytest.mark.asyncio
async def test_configure_exporter_disable():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.configure_exporter("snmpd", enable=False)

    assert result["success"] is True
    assert result["enabled"] is False


@pytest.mark.asyncio
async def test_configure_exporter_failure():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.configure_exporter("bad", enable=True)

    assert result["success"] is False


# ---------------------------------------------------------------------------
# exporter_restart
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exporter_restart():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.exporter_restart("node_exporter")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_exporter_restart_failure():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await monitoring.exporter_restart("bad")

    assert result["success"] is False


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.monitoring.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        await monitoring._run("systemctl restart node_exporter", sudo=True)
        cmd = " ".join(m.call_args[0])
        assert cmd.startswith("sudo ")
