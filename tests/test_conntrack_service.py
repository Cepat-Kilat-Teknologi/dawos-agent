"""Tests for services/conntrack.py — conntrack tuning."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import conntrack


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config():
    calls = iter(["262144", "50000", "65536"])

    async def fake_shell(*args, **kw):
        return _mock_proc(next(calls))

    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        side_effect=fake_shell,
    ):
        result = await conntrack.get_config()

    assert result["table_size"] == 262144
    assert result["current_count"] == 50000
    assert result["hash_size"] == 65536
    assert result["usage_percent"] == pytest.approx(19.1, abs=0.1)


@pytest.mark.asyncio
async def test_get_config_zero_max():
    """Cover zero-division guard."""
    calls = iter(["0", "0", "0"])

    async def fake_shell(*args, **kw):
        return _mock_proc(next(calls))

    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        side_effect=fake_shell,
    ):
        result = await conntrack.get_config()

    assert result["usage_percent"] == 0.0


# ---------------------------------------------------------------------------
# set_table_size
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_table_size():
    proc = _mock_proc("500000")
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await conntrack.set_table_size(500000)

    assert "table_size" in result


# ---------------------------------------------------------------------------
# timeouts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_timeouts():
    proc = _mock_proc("300")
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await conntrack.get_timeouts()

    assert "tcp_timeout_established" in result
    assert result["tcp_timeout_established"] == 300


@pytest.mark.asyncio
async def test_set_timeout():
    proc = _mock_proc("600")
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await conntrack.set_timeout("tcp_timeout_established", 600)

    assert "tcp_timeout_established" in result


@pytest.mark.asyncio
async def test_set_timeout_invalid_key():
    with pytest.raises(ValueError, match="Unknown timeout key"):
        await conntrack.set_timeout("bogus_key", 60)


@pytest.mark.asyncio
async def test_set_table_size_failure():
    """A non-zero sysctl exit must raise, not report a false success."""
    proc = _mock_proc("", 1)
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(RuntimeError, match="nf_conntrack_max"):
            await conntrack.set_table_size(500000)


@pytest.mark.asyncio
async def test_set_table_size_persist_failure():
    """A failed persist (tee) must raise even if the live sysctl succeeded."""
    procs = [_mock_proc("500000", 0), _mock_proc("", 1)]
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        side_effect=procs,
    ):
        with pytest.raises(RuntimeError, match="persist"):
            await conntrack.set_table_size(500000)


@pytest.mark.asyncio
async def test_set_timeout_failure():
    """A non-zero sysctl exit must raise, not report a false success."""
    proc = _mock_proc("", 1)
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(RuntimeError, match="tcp_timeout_established"):
            await conntrack.set_timeout("tcp_timeout_established", 600)


@pytest.mark.asyncio
async def test_apply_profile_failure():
    """A non-zero sysctl exit while applying a profile must raise."""
    proc = _mock_proc("", 1)
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        with pytest.raises(RuntimeError, match="Failed to apply profile"):
            await conntrack.apply_profile("gaming")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

LSMOD_OUTPUT = """\
Module                  Size  Used by
nf_conntrack_ftp       20480  0
nf_conntrack_sip       40960  1
nf_conntrack          172032  5 nf_conntrack_ftp,nf_conntrack_sip
"""


@pytest.mark.asyncio
async def test_list_helpers():
    proc = _mock_proc(LSMOD_OUTPUT)
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await conntrack.list_helpers()

    assert len(result) == 2
    assert result[0]["module"] == "nf_conntrack_ftp"


@pytest.mark.asyncio
async def test_list_helpers_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await conntrack.list_helpers()

    assert result == []


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------


def test_list_profiles():
    profiles = conntrack.list_profiles()
    assert "default" in profiles
    assert "gaming" in profiles
    assert "streaming" in profiles


@pytest.mark.asyncio
async def test_apply_profile():
    proc = _mock_proc("300")
    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await conntrack.apply_profile("gaming")

    assert "tcp_timeout_established" in result


@pytest.mark.asyncio
async def test_apply_profile_unknown():
    with pytest.raises(ValueError, match="Unknown profile"):
        await conntrack.apply_profile("nonexistent")


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------


def test_safe_int():
    assert conntrack._safe_int("42") == 42
    assert conntrack._safe_int("abc") == 0
    assert conntrack._safe_int("") == 0


# ---------------------------------------------------------------------------
# flush_table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flush_table():
    calls = iter(["1500", ""])

    async def fake_shell(*args, **kw):
        val = next(calls)
        return _mock_proc(val)

    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        side_effect=fake_shell,
    ):
        result = await conntrack.flush_table()

    assert result["success"] is True
    assert result["message"] == "Conntrack table flushed"
    assert result["entries_before"] == 1500


@pytest.mark.asyncio
async def test_flush_table_failure():
    calls = iter(["500", ""])

    async def fake_shell(*args, **kw):
        val = next(calls)
        cmd = " ".join(args)
        if "conntrack -F" in cmd:
            return _mock_proc(val, returncode=1)
        return _mock_proc(val)

    with patch(
        "dawos_agent.services.conntrack.asyncio.create_subprocess_exec",
        side_effect=fake_shell,
    ):
        with pytest.raises(RuntimeError, match="Failed to flush"):
            await conntrack.flush_table()
