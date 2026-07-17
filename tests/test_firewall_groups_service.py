"""Tests for services/firewall_groups.py — address/network/port groups."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import firewall_groups


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# list_groups
# ---------------------------------------------------------------------------

NFT_SETS = """\
table inet filter {
  set blocked_ips {
    type ipv4_addr
    elements = { 10.0.0.1, 10.0.0.2 }
  }
  set allowed_ports {
    type inet_service
    elements = { 80, 443 }
  }
}
"""


@pytest.mark.asyncio
async def test_list_groups():
    proc = _mock_proc(NFT_SETS)
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.list_groups()

    assert result["count"] == 2
    assert result["groups"][0]["name"] == "blocked_ips"
    assert result["groups"][0]["type"] == "ipv4_addr"
    assert "10.0.0.1" in result["groups"][0]["elements"]
    assert result["groups"][1]["name"] == "allowed_ports"


@pytest.mark.asyncio
async def test_list_groups_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.list_groups()

    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_groups_empty():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.list_groups()

    assert result["count"] == 0


# ---------------------------------------------------------------------------
# create_group
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_group_address():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.create_group("blocked", "address")

    assert result["success"] is True
    assert result["name"] == "blocked"


@pytest.mark.asyncio
async def test_create_group_network():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.create_group("nets", "network")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_create_group_port():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.create_group("webports", "port")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_create_group_with_elements():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.create_group(
            "ips", "address", elements=["10.0.0.1", "10.0.0.2"]
        )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_create_group_invalid_type():
    with pytest.raises(ValueError, match="Invalid group type"):
        await firewall_groups.create_group("bad", "invalid_type")


@pytest.mark.asyncio
async def test_create_group_failure():
    """Table ensure succeeds but set creation fails → RuntimeError."""
    call_count = 0

    async def _side_effect(*args, **kw):
        nonlocal call_count
        call_count += 1
        # First call = _ensure_table (succeed), second = nft add set (fail)
        if call_count <= 1:
            return _mock_proc("")
        return _mock_proc("error", returncode=1)

    with (
        patch(
            "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
            side_effect=_side_effect,
        ),
        pytest.raises(RuntimeError, match="Failed to create group"),
    ):
        await firewall_groups.create_group("fail", "address")


@pytest.mark.asyncio
async def test_create_group_ensure_table_failure():
    """Table ensure itself fails → RuntimeError."""
    proc = _mock_proc("error", returncode=1)
    with (
        patch(
            "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="Cannot create nftables table"),
    ):
        await firewall_groups.create_group("fail", "address")


@pytest.mark.asyncio
async def test_create_group_elements_failure():
    """Table + set creation succeed but adding elements fails."""
    call_count = 0

    async def _side_effect(*args, **kw):
        nonlocal call_count
        call_count += 1
        # Calls 1 (_ensure_table) and 2 (nft add set) succeed; 3 (add element) fails
        if call_count <= 2:
            return _mock_proc("")
        return _mock_proc("error", returncode=1)

    with (
        patch(
            "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
            side_effect=_side_effect,
        ),
        pytest.raises(RuntimeError, match="failed to add elements"),
    ):
        await firewall_groups.create_group("ips", "address", elements=["10.0.0.1"])


# ---------------------------------------------------------------------------
# delete_group
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_group():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.delete_group("blocked")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_delete_group_failure():
    proc = _mock_proc("not found", returncode=1)
    with (
        patch(
            "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="Failed to delete group"),
    ):
        await firewall_groups.delete_group("nope")


# ---------------------------------------------------------------------------
# add_members
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_members():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await firewall_groups.add_members("blocked", ["10.0.0.3"])

    assert result["success"] is True


@pytest.mark.asyncio
async def test_add_members_failure():
    proc = _mock_proc("error", returncode=1)
    with (
        patch(
            "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="Failed to add members"),
    ):
        await firewall_groups.add_members("nope", ["10.0.0.1"])


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.firewall_groups.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        await firewall_groups._run("nft list sets", sudo=True)
        cmd = " ".join(m.call_args[0])
        assert cmd.startswith("sudo ")
