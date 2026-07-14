"""Tests for services/ip_pool.py — IP pool CRUD."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import ip_pool

SAMPLE_CONFIG = """\
[ip-pool]
gw=10.0.0.1
10.0.0.0/24,customers
10.1.0.0/24,staff
"""


@pytest.fixture()
def config_file(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text(SAMPLE_CONFIG)
    return p


# ---------------------------------------------------------------------------
# list_pools
# ---------------------------------------------------------------------------


def test_list_pools(config_file):
    pools = ip_pool.list_pools(config_path=config_file)
    assert len(pools) == 2
    assert pools[0]["name"] == "customers"
    assert pools[0]["range"] == "10.0.0.0/24"
    assert pools[1]["name"] == "staff"


def test_list_pools_unnamed(tmp_path):
    """Pool without a name label uses CIDR as name."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[ip-pool]\n10.0.0.0/24\n")
    pools = ip_pool.list_pools(config_path=p)
    assert len(pools) == 1
    assert pools[0]["name"] == "10.0.0.0/24"


def test_list_pools_empty(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[ip-pool]\ngw=10.0.0.1\n")
    pools = ip_pool.list_pools(config_path=p)
    assert pools == []


def test_list_pools_missing():
    with pytest.raises(FileNotFoundError):
        ip_pool.list_pools(config_path=Path("/nonexistent"))


# ---------------------------------------------------------------------------
# add_pool
# ---------------------------------------------------------------------------


def test_add_pool(config_file):
    with patch.object(ip_pool.config_manager, "write_config"):
        result = ip_pool.add_pool("vip", "172.16.0.0/24", config_path=config_file)
    assert "vip" in result


def test_add_pool_duplicate(config_file):
    with pytest.raises(ValueError, match="already exists"):
        ip_pool.add_pool("customers", "10.2.0.0/24", config_path=config_file)


def test_add_pool_invalid_cidr(config_file):
    with pytest.raises(ValueError, match="Invalid CIDR"):
        ip_pool.add_pool("bad", "not-a-cidr", config_path=config_file)


def test_add_pool_at_eof(tmp_path):
    """Cover [ip-pool] as last section."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[ip-pool]\n10.0.0.0/24,existing\n")

    written = {}

    def capture(content, **_kw):
        written["content"] = content

    with patch.object(ip_pool.config_manager, "write_config", side_effect=capture):
        ip_pool.add_pool("new-pool", "172.16.0.0/24", config_path=p)

    assert "172.16.0.0/24,new-pool" in written["content"]


def test_add_pool_missing():
    with pytest.raises(FileNotFoundError):
        ip_pool.add_pool("x", "10.0.0.0/24", config_path=Path("/nonexistent"))


def test_add_pool_section_transition(tmp_path):
    """Cover insertion when leaving [ip-pool] for another section."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[ip-pool]\n10.0.0.0/24,existing\n[other]\nfoo=bar\n")

    written = {}

    def capture(content, **_kw):
        written["content"] = content

    with patch.object(ip_pool.config_manager, "write_config", side_effect=capture):
        ip_pool.add_pool("second", "10.1.0.0/24", config_path=p)

    assert "10.1.0.0/24,second" in written["content"]


# ---------------------------------------------------------------------------
# remove_pool
# ---------------------------------------------------------------------------


def test_remove_pool(config_file):
    with patch.object(ip_pool.config_manager, "write_config"):
        result = ip_pool.remove_pool("customers", config_path=config_file)
    assert "customers" in result


def test_remove_pool_not_found(config_file):
    with pytest.raises(ValueError, match="not found"):
        ip_pool.remove_pool("ghost", config_path=config_file)


def test_remove_pool_missing():
    with pytest.raises(FileNotFoundError):
        ip_pool.remove_pool("x", config_path=Path("/nonexistent"))


# ---------------------------------------------------------------------------
# pool_usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_usage():
    with patch.object(
        ip_pool.accel,
        "show_ippool",
        AsyncMock(return_value={"used": "100", "total": "500", "available": "400"}),
    ):
        result = await ip_pool.pool_usage()

    assert result["used"] == "100"
    assert result["total"] == "500"


# ---------------------------------------------------------------------------
# _cidr_host_count
# ---------------------------------------------------------------------------


def test_cidr_host_count_24():
    """A /24 has 254 usable hosts."""
    assert ip_pool._cidr_host_count("10.0.0.0/24") == 254


def test_cidr_host_count_32():
    """A /32 has 1 address (single host)."""
    assert ip_pool._cidr_host_count("10.0.0.1/32") == 1


def test_cidr_host_count_31():
    """A /31 has 2 addresses (point-to-point)."""
    assert ip_pool._cidr_host_count("10.0.0.0/31") == 2


def test_cidr_host_count_16():
    """A /16 has 65534 usable hosts."""
    assert ip_pool._cidr_host_count("10.0.0.0/16") == 65534


def test_cidr_host_count_invalid():
    """Invalid CIDR returns 0."""
    assert ip_pool._cidr_host_count("not-a-cidr") == 0


# ---------------------------------------------------------------------------
# get_pool_detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pool_detail_with_assignments(config_file):
    """get_pool_detail() maps session IPs to their pools."""
    mock_sessions = [
        {"ip": "10.0.0.5", "username": "user1"},
        {"ip": "10.0.0.10", "username": "user2"},
        {"ip": "10.1.0.3", "username": "staff1"},
    ]
    with patch.object(
        ip_pool.accel,
        "show_sessions",
        AsyncMock(return_value=mock_sessions),
    ):
        result = await ip_pool.get_pool_detail(config_path=config_file)

    assert result["total_pools"] == 2
    assert result["total_used"] == 3
    assert result["total_capacity"] == 254 * 2  # two /24 pools

    # customers pool: 2 sessions
    customers = result["pools"][0]
    assert customers["name"] == "customers"
    assert customers["used"] == 2
    assert len(customers["assignments"]) == 2
    assert customers["assignments"][0]["username"] == "user1"

    # staff pool: 1 session
    staff = result["pools"][1]
    assert staff["name"] == "staff"
    assert staff["used"] == 1


@pytest.mark.asyncio
async def test_get_pool_detail_no_sessions(config_file):
    """get_pool_detail() with no active sessions shows zero usage."""
    with patch.object(
        ip_pool.accel,
        "show_sessions",
        AsyncMock(return_value=[]),
    ):
        result = await ip_pool.get_pool_detail(config_path=config_file)

    assert result["total_used"] == 0
    assert result["total_capacity"] == 254 * 2
    for pool in result["pools"]:
        assert pool["used"] == 0
        assert pool["assignments"] == []


@pytest.mark.asyncio
async def test_get_pool_detail_ip_outside_pools(config_file):
    """Sessions with IPs outside any pool are not counted."""
    mock_sessions = [
        {"ip": "192.168.1.1", "username": "rogue"},
    ]
    with patch.object(
        ip_pool.accel,
        "show_sessions",
        AsyncMock(return_value=mock_sessions),
    ):
        result = await ip_pool.get_pool_detail(config_path=config_file)

    assert result["total_used"] == 0


@pytest.mark.asyncio
async def test_get_pool_detail_empty_ip_skipped(config_file):
    """Sessions with empty IP are skipped."""
    mock_sessions = [
        {"ip": "", "username": "user1"},
        {"ip": "10.0.0.5", "username": "user2"},
    ]
    with patch.object(
        ip_pool.accel,
        "show_sessions",
        AsyncMock(return_value=mock_sessions),
    ):
        result = await ip_pool.get_pool_detail(config_path=config_file)

    assert result["total_used"] == 1


@pytest.mark.asyncio
async def test_get_pool_detail_invalid_session_ip(config_file):
    """Sessions with invalid IP are skipped without error."""
    mock_sessions = [
        {"ip": "not-an-ip", "username": "baduser"},
        {"ip": "10.0.0.5", "username": "good"},
    ]
    with patch.object(
        ip_pool.accel,
        "show_sessions",
        AsyncMock(return_value=mock_sessions),
    ):
        result = await ip_pool.get_pool_detail(config_path=config_file)

    assert result["total_used"] == 1


@pytest.mark.asyncio
async def test_get_pool_detail_invalid_pool_cidr(tmp_path):
    """Pools with regex-valid but IP-invalid CIDR get 0 capacity."""
    p = tmp_path / "accel-ppp.conf"
    # 999.x is regex-valid (\d+.\d+...) but ipaddress rejects it
    p.write_text("[ip-pool]\n999.999.999.999/24,badpool\n")

    with patch.object(
        ip_pool.accel,
        "show_sessions",
        AsyncMock(return_value=[]),
    ):
        result = await ip_pool.get_pool_detail(config_path=p)

    assert result["total_pools"] == 1
    assert result["pools"][0]["total_ips"] == 0
    assert result["pools"][0]["utilization_pct"] == 0.0


@pytest.mark.asyncio
async def test_get_pool_detail_utilization_pct(tmp_path):
    """Utilization percentage is calculated correctly."""
    p = tmp_path / "accel-ppp.conf"
    # /30 = 2 usable hosts
    p.write_text("[ip-pool]\n10.0.0.0/30,small\n")

    mock_sessions = [{"ip": "10.0.0.1", "username": "u1"}]
    with patch.object(
        ip_pool.accel,
        "show_sessions",
        AsyncMock(return_value=mock_sessions),
    ):
        result = await ip_pool.get_pool_detail(config_path=p)

    pool = result["pools"][0]
    assert pool["total_ips"] == 2  # /30 minus net+bcast
    assert pool["used"] == 1
    assert pool["utilization_pct"] == 50.0


@pytest.mark.asyncio
async def test_get_pool_detail_file_not_found():
    """get_pool_detail() raises FileNotFoundError for missing config."""
    with pytest.raises(FileNotFoundError):
        await ip_pool.get_pool_detail(config_path=Path("/nonexistent"))
