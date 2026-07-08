"""Tests for services/dns_forwarding.py — dnsmasq wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import dns_forwarding


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_running():
    calls = iter(
        [
            _mock_proc("active"),  # systemctl is-active
            _mock_proc("3"),  # grep -c server=
        ]
    )

    async def fake_shell(cmd, **kw):
        return next(calls)

    with patch(
        "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
        side_effect=fake_shell,
    ):
        result = await dns_forwarding.status()

    assert result["running"] is True
    assert result["upstream_count"] == 3


@pytest.mark.asyncio
async def test_status_stopped():
    proc = _mock_proc("inactive", returncode=3)
    with patch(
        "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dns_forwarding.status()

    assert result["running"] is False
    assert result["upstream_count"] == 0


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_config():
    calls = iter(
        [
            _mock_proc("server=8.8.8.8\nserver=1.1.1.1"),  # grep server=
            _mock_proc("listen-address=127.0.0.1"),  # grep listen-address=
            _mock_proc("cache-size=5000"),  # grep cache-size=
        ]
    )

    async def fake_shell(cmd, **kw):
        return next(calls)

    with patch(
        "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
        side_effect=fake_shell,
    ):
        result = await dns_forwarding.get_config()

    assert result["servers"] == ["8.8.8.8", "1.1.1.1"]
    assert result["listen_address"] == "127.0.0.1"
    assert result["cache_size"] == 5000


@pytest.mark.asyncio
async def test_get_config_empty():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dns_forwarding.get_config()

    assert result["servers"] == []
    assert result["cache_size"] == 150  # default


# ---------------------------------------------------------------------------
# set_forwarders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_forwarders():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dns_forwarding.set_forwarders(["8.8.8.8", "1.1.1.1"], 2000)

    assert result["servers"] == ["8.8.8.8", "1.1.1.1"]
    assert result["cache_size"] == 2000


@pytest.mark.asyncio
async def test_set_forwarders_reload_fail():
    calls = iter(
        [
            _mock_proc("active"),  # systemctl is-active dnsmasq
            _mock_proc(""),  # tee config
            _mock_proc("fail", returncode=1),  # systemctl reload
        ]
    )

    async def fake_shell(cmd, **kw):
        return next(calls)

    with (
        patch(
            "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
            side_effect=fake_shell,
        ),
        pytest.raises(RuntimeError, match="Failed to reload"),
    ):
        await dns_forwarding.set_forwarders(["8.8.8.8"])


@pytest.mark.asyncio
async def test_set_forwarders_dnsmasq_not_installed():
    proc = _mock_proc("inactive", returncode=3)
    with (
        patch(
            "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="dnsmasq is not installed"),
    ):
        await dns_forwarding.set_forwarders(["8.8.8.8"])


# ---------------------------------------------------------------------------
# flush_cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flush_cache():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await dns_forwarding.flush_cache()

    assert result["flushed"] is True


@pytest.mark.asyncio
async def test_flush_cache_fail():
    calls = iter(
        [
            _mock_proc("active"),  # systemctl is-active dnsmasq
            _mock_proc("fail", returncode=1),  # systemctl kill -s HUP
        ]
    )

    async def fake_shell(cmd, **kw):
        return next(calls)

    with (
        patch(
            "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
            side_effect=fake_shell,
        ),
        pytest.raises(RuntimeError, match="Failed to flush"),
    ):
        await dns_forwarding.flush_cache()


@pytest.mark.asyncio
async def test_flush_cache_dnsmasq_not_installed():
    proc = _mock_proc("inactive", returncode=3)
    with (
        patch(
            "dawos_agent.services.dns_forwarding.asyncio.create_subprocess_shell",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="dnsmasq is not installed"),
    ):
        await dns_forwarding.flush_cache()


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------


def test_safe_int():
    assert dns_forwarding._safe_int("42") == 42
    assert dns_forwarding._safe_int("abc") == 0
