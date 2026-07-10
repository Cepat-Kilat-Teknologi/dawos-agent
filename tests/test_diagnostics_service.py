"""Tests for services/diagnostics.py — BNG health checks."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import diagnostics

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_service_running():
    proc = _mock_proc("active")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_service()

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_check_service_stopped():
    proc = _mock_proc("inactive", returncode=3)
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_service()

    assert result["status"] == "fail"


@pytest.mark.asyncio
async def test_check_pppoe_loaded():
    proc = _mock_proc("pppoe                  12345  0")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_pppoe()

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_check_pppoe_missing():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_pppoe()

    assert result["status"] == "warn"


@pytest.mark.asyncio
async def test_check_nat_active():
    proc = _mock_proc("table dawos-nat { masquerade }")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_nat()

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_check_nat_missing():
    proc = _mock_proc("table filter { }")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_nat()

    assert result["status"] == "warn"


@pytest.mark.asyncio
async def test_check_firewall_active():
    proc = _mock_proc("active")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_firewall()

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_check_firewall_inactive():
    proc = _mock_proc("inactive", returncode=3)
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_firewall()

    assert result["status"] == "warn"


@pytest.mark.asyncio
async def test_check_conntrack_ok():
    proc = _mock_proc("524288")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_conntrack()

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_check_conntrack_low():
    proc = _mock_proc("65536")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_conntrack()

    assert result["status"] == "warn"


@pytest.mark.asyncio
async def test_check_conntrack_unavailable():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_conntrack()

    assert result["status"] == "warn"
    assert "not available" in result["detail"]


@pytest.mark.asyncio
async def test_check_pool_ok():
    with patch(
        "dawos_agent.services.accel.show_ippool",
        new_callable=AsyncMock,
        return_value={"used": "10", "total": "100", "available": "90"},
    ):
        result = await diagnostics.check_pool()

    assert result["status"] == "ok"
    assert "90/100" in result["detail"]


@pytest.mark.asyncio
async def test_check_pool_exhausted():
    with patch(
        "dawos_agent.services.accel.show_ippool",
        new_callable=AsyncMock,
        return_value={"used": "100", "total": "100", "available": "0"},
    ):
        result = await diagnostics.check_pool()

    assert result["status"] == "fail"


@pytest.mark.asyncio
async def test_check_pool_no_pool():
    with patch(
        "dawos_agent.services.accel.show_ippool",
        new_callable=AsyncMock,
        return_value={"used": "0", "total": "0", "available": "0"},
    ):
        result = await diagnostics.check_pool()

    assert result["status"] == "warn"


@pytest.mark.asyncio
async def test_check_pool_error():
    with patch(
        "dawos_agent.services.accel.show_ippool",
        new_callable=AsyncMock,
        side_effect=Exception("connection failed"),
    ):
        result = await diagnostics.check_pool()

    assert result["status"] == "warn"


@pytest.mark.asyncio
async def test_check_internet_ok():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_internet()

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_check_internet_fail():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.check_internet()

    assert result["status"] == "fail"


@pytest.mark.asyncio
async def test_check_snmp_running():
    # systemctl → active (rc=0), ss → shows port 161 (rc=0)
    proc_active = _mock_proc("active")
    proc_ss = _mock_proc(
        "Netid  State  Recv-Q Send-Q  Local Address:Port\nudp    UNCONN 0      0      0.0.0.0:161"
    )
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        side_effect=[proc_active, proc_ss],
    ):
        result = await diagnostics.check_snmp()

    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_check_snmp_not_running():
    # systemctl → inactive (rc=3), ss → no output (rc=1)
    proc_inactive = _mock_proc("inactive", returncode=3)
    proc_ss = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        side_effect=[proc_inactive, proc_ss],
    ):
        result = await diagnostics.check_snmp()

    assert result["status"] == "warn"
    assert "not running" in result["detail"]


@pytest.mark.asyncio
async def test_check_snmp_running_port_closed():
    # systemctl → active (rc=0), ss → empty/no 161 (rc=0)
    proc_active = _mock_proc("active")
    proc_ss = _mock_proc("Netid  State  Recv-Q Send-Q  Local Address:Port")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        side_effect=[proc_active, proc_ss],
    ):
        result = await diagnostics.check_snmp()

    assert result["status"] == "warn"
    assert "port 161 closed" in result["detail"]


# ---------------------------------------------------------------------------
# get_conntrack / set_conntrack
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_conntrack_ok():
    proc = _mock_proc("524288")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.get_conntrack()

    assert result["current_max"] == 524288
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_get_conntrack_warn():
    proc = _mock_proc("65536")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.get_conntrack()

    assert result["status"] == "warn"
    assert "recommend" in result["detail"]


@pytest.mark.asyncio
async def test_get_conntrack_unavailable():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.get_conntrack()

    assert result["current_max"] == 0
    assert result["status"] == "warn"


@pytest.mark.asyncio
async def test_set_conntrack():
    proc = _mock_proc("524288")
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await diagnostics.set_conntrack(524288)

    assert result["current_max"] == 524288


# ---------------------------------------------------------------------------
# snmp_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snmp_status():
    proc_active = _mock_proc("active")
    proc_ss = _mock_proc(
        "Netid  State  Recv-Q Send-Q  Local Address:Port\nudp    UNCONN 0      0      0.0.0.0:161"
    )
    with patch(
        "dawos_agent.services.diagnostics.asyncio.create_subprocess_shell",
        side_effect=[proc_active, proc_ss],
    ):
        result = await diagnostics.snmp_status()

    assert result["name"] == "snmp"


# ---------------------------------------------------------------------------
# run_doctor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_doctor():
    with (
        patch(
            "dawos_agent.services.diagnostics.check_service",
            new_callable=AsyncMock,
            return_value={"name": "service", "status": "ok", "detail": ""},
        ),
        patch(
            "dawos_agent.services.diagnostics.check_pppoe",
            new_callable=AsyncMock,
            return_value={"name": "pppoe", "status": "ok", "detail": ""},
        ),
        patch(
            "dawos_agent.services.diagnostics.check_nat",
            new_callable=AsyncMock,
            return_value={"name": "nat", "status": "warn", "detail": ""},
        ),
        patch(
            "dawos_agent.services.diagnostics.check_firewall",
            new_callable=AsyncMock,
            return_value={"name": "firewall", "status": "ok", "detail": ""},
        ),
        patch(
            "dawos_agent.services.diagnostics.check_conntrack",
            new_callable=AsyncMock,
            return_value={"name": "conntrack", "status": "ok", "detail": ""},
        ),
        patch(
            "dawos_agent.services.diagnostics.check_pool",
            new_callable=AsyncMock,
            return_value={"name": "pool", "status": "ok", "detail": ""},
        ),
        patch(
            "dawos_agent.services.diagnostics.check_internet",
            new_callable=AsyncMock,
            return_value={"name": "internet", "status": "fail", "detail": ""},
        ),
        patch(
            "dawos_agent.services.diagnostics.check_snmp",
            new_callable=AsyncMock,
            return_value={"name": "snmp", "status": "ok", "detail": ""},
        ),
    ):
        result = await diagnostics.run_doctor()

    assert result["total"] == 8
    assert result["fails"] == 1
    assert result["warns"] == 1
    assert result["healthy"] is False
