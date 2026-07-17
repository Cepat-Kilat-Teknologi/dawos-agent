"""Tests for accel service layer — async functions with mocked subprocess."""

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services.accel import (
    ifname_of,
    mac_filter,
    reload_config,
    run_cmd,
    shaper_change,
    shaper_restore,
    show_ippool,
    show_sessions,
    show_stat,
    show_version,
    shutdown,
    shutdown_cancel,
    terminate_session,
)


def _mock_process(stdout=b"", stderr=b"", returncode=0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc


@pytest.mark.asyncio
async def test_run_cmd_success():
    proc = _mock_process(stdout=b"output here")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await run_cmd("show stat")

    assert result == "output here"


@pytest.mark.asyncio
async def test_run_cmd_failure():
    proc = _mock_process(stderr=b"connection refused", returncode=1)

    with (
        patch(
            "dawos_agent.services.accel.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="connection refused"),
    ):
        await run_cmd("show stat")


@pytest.mark.asyncio
async def test_run_cmd_failure_stdout_fallback():
    proc = _mock_process(stdout=b"error in stdout", stderr=b"", returncode=1)

    with (
        patch(
            "dawos_agent.services.accel.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="error in stdout"),
    ):
        await run_cmd("bad cmd")


@pytest.mark.asyncio
async def test_show_sessions():
    table = " ifname | username\n-----+------\n ppp0 | user1\n"
    proc = _mock_process(stdout=table.encode())

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await show_sessions("ifname,username")

    assert len(result) == 1
    assert result[0]["username"] == "user1"


@pytest.mark.asyncio
async def test_show_stat():
    text = (
        "uptime: 1:00\ncpu: 2%\nsessions:\n  active: 5\n  starting: 1\n  finishing: 0\n"
    )
    proc = _mock_process(stdout=text.encode())

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await show_stat()

    assert result["sessions"]["active"] == 5


@pytest.mark.asyncio
async def test_show_ippool():
    text = "  used: 10\n  total: 100\n  available: 90\n"
    proc = _mock_process(stdout=text.encode())

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await show_ippool()

    assert result["used"] == "10"


@pytest.mark.asyncio
async def test_show_version():
    proc = _mock_process(stdout=b"1.13.0")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await show_version()

    assert result == "1.13.0"


@pytest.mark.asyncio
async def test_reload_config():
    proc = _mock_process(stdout=b"")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await reload_config()

    assert result == ""


@pytest.mark.asyncio
async def test_terminate_by_username():
    proc = _mock_process(stdout=b"")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        await terminate_session(username="user1")


@pytest.mark.asyncio
async def test_terminate_by_ifname():
    proc = _mock_process(stdout=b"")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        await terminate_session(ifname="ppp0")


@pytest.mark.asyncio
async def test_terminate_no_target():
    with pytest.raises(ValueError, match="Either username or ifname"):
        await terminate_session()


# ---------------------------------------------------------------------------
# ifname_of
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ifname_of_found():
    output = " ifname\n-------\n ppp0\n"
    proc = _mock_process(stdout=output.encode())

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await ifname_of("user1")

    assert result == "ppp0"


@pytest.mark.asyncio
async def test_ifname_of_not_found():
    output = " ifname\n-------\n"
    proc = _mock_process(stdout=output.encode())

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await ifname_of("offline")

    assert result is None


# ---------------------------------------------------------------------------
# shaper_change / shaper_restore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shaper_change():
    proc = _mock_process(stdout=b"shaper changed")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await shaper_change("ppp0", "20000/5000")

    assert result == "shaper changed"


@pytest.mark.asyncio
async def test_shaper_restore():
    proc = _mock_process(stdout=b"shaper restored")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await shaper_restore("ppp0")

    assert result == "shaper restored"


# ---------------------------------------------------------------------------
# mac_filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mac_filter_show():
    proc = _mock_process(stdout=b"AA:BB:CC:DD:EE:FF")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await mac_filter("show")

    assert "AA:BB:CC:DD:EE:FF" in result


@pytest.mark.asyncio
async def test_mac_filter_add():
    proc = _mock_process(stdout=b"ok")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await mac_filter("add", "AA:BB:CC:DD:EE:FF")

    assert result == "ok"


# ---------------------------------------------------------------------------
# shutdown / shutdown_cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_soft():
    proc = _mock_process(stdout=b"")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await shutdown("soft")

    assert result == ""


@pytest.mark.asyncio
async def test_shutdown_hard():
    proc = _mock_process(stdout=b"")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await shutdown("hard")

    assert result == ""


@pytest.mark.asyncio
async def test_shutdown_cancel():
    proc = _mock_process(stdout=b"")

    with patch(
        "dawos_agent.services.accel.asyncio.create_subprocess_exec", return_value=proc
    ):
        result = await shutdown_cancel()

    assert result == ""
