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
