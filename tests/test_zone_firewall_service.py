"""Tests for services/zone_firewall.py — zone-based firewall."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import zone_firewall


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# list_zones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_zones():
    out = "table inet filter\ntable inet nat\n"
    proc = _mock_proc(out)
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.list_zones()

    assert result["count"] == 2
    assert result["zones"][0]["name"] == "filter"
    assert result["zones"][1]["name"] == "nat"


@pytest.mark.asyncio
async def test_list_zones_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.list_zones()

    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_zones_empty():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.list_zones()

    assert result["count"] == 0


# ---------------------------------------------------------------------------
# zone_detail
# ---------------------------------------------------------------------------

NFT_TABLE = """\
table inet filter {
  chain input {
    type filter hook input priority 0; policy accept;
    ct state established,related accept
    iifname "lo" accept
  }
  chain forward {
    type filter hook forward priority 0; policy accept;
  }
}
"""


@pytest.mark.asyncio
async def test_zone_detail():
    proc = _mock_proc(NFT_TABLE)
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.zone_detail("filter")

    assert result["found"] is True
    assert result["zone"] == "filter"
    assert len(result["rules"]) >= 1


@pytest.mark.asyncio
async def test_zone_detail_not_found():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.zone_detail("nonexistent")

    assert result["found"] is False


# ---------------------------------------------------------------------------
# create_zone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_zone():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.create_zone("dmz")

    assert result["success"] is True
    assert "dmz" in result["message"]


@pytest.mark.asyncio
async def test_create_zone_with_interfaces():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.create_zone("lan", interfaces=["eth0", "eth1"])

    assert result["success"] is True
    assert "eth0" in result["message"]


@pytest.mark.asyncio
async def test_create_zone_failure():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.create_zone("bad")

    assert result["success"] is False


# ---------------------------------------------------------------------------
# delete_zone
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_zone():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.delete_zone("dmz")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_delete_zone_failure():
    proc = _mock_proc("no such table", returncode=1)
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await zone_firewall.delete_zone("nope")

    assert result["success"] is False


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.zone_firewall.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        await zone_firewall._run("nft list tables", sudo=True)
        cmd = " ".join(m.call_args[0])
        assert cmd.startswith("sudo ")
