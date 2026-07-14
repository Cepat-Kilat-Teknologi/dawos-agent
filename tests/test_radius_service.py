"""Tests for RADIUS diagnostics service — pure functions + async mocks."""

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services.radius import (
    _parse_server_line,
    _tcp_reachable,
    check_radius,
    get_radius_status,
    parse_radius_config,
    read_radius_config,
)

# ---------------------------------------------------------------------------
# _parse_server_line
# ---------------------------------------------------------------------------


def test_parse_server_line_full():
    """server= line with address, secret, both ports."""
    result = _parse_server_line(
        "server=10.0.0.1,mysecret,auth-port=1812,acct-port=1813"
    )
    assert result is not None
    assert result["address"] == "10.0.0.1"
    assert result["auth_port"] == 1812
    assert result["acct_port"] == 1813


def test_parse_server_line_auth_only():
    """auth-server= line with custom port."""
    result = _parse_server_line("auth-server=10.0.0.2,secret,auth-port=1815")
    assert result is not None
    assert result["address"] == "10.0.0.2"
    assert result["auth_port"] == 1815
    assert result["acct_port"] == 1813  # default


def test_parse_server_line_acct_only():
    """acct-server= line with custom port."""
    result = _parse_server_line("acct-server=10.0.0.3,secret,acct-port=1814")
    assert result is not None
    assert result["address"] == "10.0.0.3"
    assert result["auth_port"] == 1812  # default
    assert result["acct_port"] == 1814


def test_parse_server_line_defaults():
    """server= line with no explicit ports uses defaults."""
    result = _parse_server_line("server=10.0.0.1,secret")
    assert result is not None
    assert result["auth_port"] == 1812
    assert result["acct_port"] == 1813


def test_parse_server_line_no_match():
    """Non-server line returns None."""
    assert _parse_server_line("timeout=3") is None
    assert _parse_server_line("nas-identifier=accel") is None
    assert _parse_server_line("") is None


# ---------------------------------------------------------------------------
# parse_radius_config
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = """\
[modules]
radius

[radius]
nas-identifier=accel-ppp
nas-ip-address=10.100.0.1
gw-ip-address=10.100.0.1
server=10.100.0.253,testing123,auth-port=1812,acct-port=1813
timeout=5
max-try=4
acct-timeout=120

[pppoe]
interface=ens19
"""


def test_parse_radius_config_full():
    """Full config parses all RADIUS fields correctly."""
    result = parse_radius_config(SAMPLE_CONFIG)
    assert result["nas_identifier"] == "accel-ppp"
    assert result["nas_ip_address"] == "10.100.0.1"
    assert result["gw_ip_address"] == "10.100.0.1"
    assert result["timeout"] == 5
    assert result["max_try"] == 4
    assert result["acct_timeout"] == 120
    assert len(result["servers"]) == 1
    srv = result["servers"][0]
    assert srv["address"] == "10.100.0.253"
    assert srv["auth_port"] == 1812
    assert srv["acct_port"] == 1813


def test_parse_radius_config_no_secret_leaked():
    """Secrets from server= lines are NOT in the output."""
    result = parse_radius_config(SAMPLE_CONFIG)
    import json

    serialised = json.dumps(result)
    assert "testing123" not in serialised


def test_parse_radius_config_multiple_servers():
    """Multiple server= lines produce multiple entries."""
    text = """\
[radius]
server=10.0.0.1,secret1,auth-port=1812
server=10.0.0.2,secret2,auth-port=1815
"""
    result = parse_radius_config(text)
    assert len(result["servers"]) == 2
    assert result["servers"][0]["address"] == "10.0.0.1"
    assert result["servers"][1]["address"] == "10.0.0.2"
    assert result["servers"][1]["auth_port"] == 1815


def test_parse_radius_config_dedup_servers():
    """Duplicate addresses are deduplicated."""
    text = """\
[radius]
auth-server=10.0.0.1,s1,auth-port=1812
acct-server=10.0.0.1,s1,acct-port=1813
"""
    result = parse_radius_config(text)
    assert len(result["servers"]) == 1


def test_parse_radius_config_empty():
    """Empty config produces safe defaults."""
    result = parse_radius_config("")
    assert result["nas_identifier"] == ""
    assert result["servers"] == []
    assert result["timeout"] == 3


def test_parse_radius_config_no_radius_section():
    """Config without [radius] section produces defaults."""
    text = "[pppoe]\ninterface=ens19\n"
    result = parse_radius_config(text)
    assert result["servers"] == []
    assert result["nas_identifier"] == ""


def test_parse_radius_config_comments_ignored():
    """Comment lines within [radius] are ignored."""
    text = """\
[radius]
# This is a comment
nas-identifier=test
#server=10.0.0.1,secret
"""
    result = parse_radius_config(text)
    assert result["nas_identifier"] == "test"
    assert result["servers"] == []


def test_parse_radius_config_non_numeric_timeout():
    """Non-numeric timeout uses default."""
    text = "[radius]\ntimeout=abc\n"
    result = parse_radius_config(text)
    assert result["timeout"] == 3


def test_parse_radius_config_non_numeric_max_try():
    """Non-numeric max-try uses default."""
    text = "[radius]\nmax-try=xyz\n"
    result = parse_radius_config(text)
    assert result["max_try"] == 3


def test_parse_radius_config_non_numeric_acct_timeout():
    """Non-numeric acct-timeout uses default."""
    text = "[radius]\nacct-timeout=bad\n"
    result = parse_radius_config(text)
    assert result["acct_timeout"] == 0


def test_parse_radius_config_other_section_keys_ignored():
    """Keys from other sections don't bleed into RADIUS result."""
    text = """\
[radius]
nas-identifier=rad1
[pppoe]
nas-identifier=pppoe-should-not-appear
"""
    result = parse_radius_config(text)
    assert result["nas_identifier"] == "rad1"


# ---------------------------------------------------------------------------
# read_radius_config (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_radius_config_reads_file(tmp_path):
    """read_radius_config() reads the config file and parses it."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text("[radius]\nnas-identifier=test-nas\n", encoding="utf-8")

    with patch("dawos_agent.services.radius.ACCEL_CONFIG", conf):
        result = await read_radius_config()

    assert result["nas_identifier"] == "test-nas"


@pytest.mark.asyncio
async def test_read_radius_config_file_not_found():
    """read_radius_config() raises FileNotFoundError for missing file."""
    from pathlib import Path

    missing = Path("/nonexistent/accel-ppp.conf")
    with (
        patch("dawos_agent.services.radius.ACCEL_CONFIG", missing),
        pytest.raises(FileNotFoundError),
    ):
        await read_radius_config()


# ---------------------------------------------------------------------------
# get_radius_status (async)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _tcp_reachable (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tcp_reachable_success():
    """_tcp_reachable() returns True when connection succeeds."""
    mock_writer = AsyncMock()
    mock_writer.close = lambda: None
    mock_writer.wait_closed = AsyncMock()

    with patch(
        "dawos_agent.services.radius.asyncio.open_connection",
        new_callable=AsyncMock,
        return_value=(AsyncMock(), mock_writer),
    ):
        result = await _tcp_reachable("10.0.0.1", 1812)

    assert result is True


@pytest.mark.asyncio
async def test_tcp_reachable_refused():
    """_tcp_reachable() returns False on connection refused."""
    with patch(
        "dawos_agent.services.radius.asyncio.open_connection",
        new_callable=AsyncMock,
        side_effect=OSError("Connection refused"),
    ):
        result = await _tcp_reachable("10.0.0.1", 1812)

    assert result is False


@pytest.mark.asyncio
async def test_tcp_reachable_timeout():
    """_tcp_reachable() returns False on timeout."""
    import asyncio

    with patch(
        "dawos_agent.services.radius.asyncio.open_connection",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError(),
    ):
        result = await _tcp_reachable("10.0.0.1", 1812)

    assert result is False


# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_radius_status_with_servers():
    """get_radius_status() summarises active/down counts."""
    mock_extended = {
        "radius": [
            {"server_address": "10.0.0.1", "state": "active"},
            {"server_address": "10.0.0.2", "state": "down"},
        ]
    }
    with patch(
        "dawos_agent.services.radius.accel.show_stat_extended",
        new_callable=AsyncMock,
        return_value=mock_extended,
    ):
        result = await get_radius_status()

    assert result["total"] == 2
    assert result["active"] == 1
    assert result["down"] == 1
    assert len(result["servers"]) == 2


@pytest.mark.asyncio
async def test_get_radius_status_empty():
    """get_radius_status() with no RADIUS servers."""
    with patch(
        "dawos_agent.services.radius.accel.show_stat_extended",
        new_callable=AsyncMock,
        return_value={"radius": []},
    ):
        result = await get_radius_status()

    assert result["total"] == 0
    assert result["active"] == 0
    assert result["down"] == 0


# ---------------------------------------------------------------------------
# check_radius (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_radius_all_healthy(tmp_path):
    """check_radius() returns healthy=True when all servers pass."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[radius]\nserver=10.0.0.1,secret,auth-port=1812\n", encoding="utf-8"
    )

    mock_status = {"servers": [{"server_address": "10.0.0.1", "state": "active"}]}

    with (
        patch("dawos_agent.services.radius.ACCEL_CONFIG", conf),
        patch(
            "dawos_agent.services.radius.get_radius_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ),
        patch(
            "dawos_agent.services.radius._tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        result = await check_radius()

    assert result["healthy"] is True
    assert result["total"] == 1
    assert result["checks"][0]["reachable"] is True
    assert result["checks"][0]["state"] == "active"


@pytest.mark.asyncio
async def test_check_radius_unreachable(tmp_path):
    """check_radius() returns healthy=False when server is unreachable."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[radius]\nserver=10.0.0.1,secret,auth-port=1812\n", encoding="utf-8"
    )

    mock_status = {"servers": [{"server_address": "10.0.0.1", "state": "active"}]}

    with (
        patch("dawos_agent.services.radius.ACCEL_CONFIG", conf),
        patch(
            "dawos_agent.services.radius.get_radius_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ),
        patch(
            "dawos_agent.services.radius._tcp_reachable",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        result = await check_radius()

    assert result["healthy"] is False
    assert result["checks"][0]["reachable"] is False
    assert "unreachable" in result["checks"][0]["detail"]


@pytest.mark.asyncio
async def test_check_radius_down_state(tmp_path):
    """check_radius() reports state=down from runtime stats."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[radius]\nserver=10.0.0.1,secret,auth-port=1812\n", encoding="utf-8"
    )

    mock_status = {"servers": [{"server_address": "10.0.0.1", "state": "down"}]}

    with (
        patch("dawos_agent.services.radius.ACCEL_CONFIG", conf),
        patch(
            "dawos_agent.services.radius.get_radius_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ),
        patch(
            "dawos_agent.services.radius._tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        result = await check_radius()

    assert result["healthy"] is False
    assert result["checks"][0]["state"] == "down"
    assert "state down" in result["checks"][0]["detail"]


@pytest.mark.asyncio
async def test_check_radius_no_config_file():
    """check_radius() returns empty checks when config file is missing."""
    from pathlib import Path

    missing = Path("/nonexistent/accel-ppp.conf")
    with patch("dawos_agent.services.radius.ACCEL_CONFIG", missing):
        result = await check_radius()

    assert result["checks"] == []
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_check_radius_status_error(tmp_path):
    """check_radius() handles runtime status errors gracefully."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[radius]\nserver=10.0.0.1,secret,auth-port=1812\n", encoding="utf-8"
    )

    with (
        patch("dawos_agent.services.radius.ACCEL_CONFIG", conf),
        patch(
            "dawos_agent.services.radius.get_radius_status",
            new_callable=AsyncMock,
            side_effect=RuntimeError("conn refused"),
        ),
        patch(
            "dawos_agent.services.radius._tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        result = await check_radius()

    # Status error → state is "unknown" but still checks reachability
    assert result["total"] == 1
    assert result["checks"][0]["state"] == "unknown"
    assert result["checks"][0]["reachable"] is True


@pytest.mark.asyncio
async def test_check_radius_unknown_state(tmp_path):
    """check_radius() marks state as unknown for unconfigured runtime servers."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[radius]\nserver=10.0.0.99,secret,auth-port=1812\n", encoding="utf-8"
    )

    # Runtime has a different server than config
    mock_status = {"servers": [{"server_address": "10.0.0.1", "state": "active"}]}

    with (
        patch("dawos_agent.services.radius.ACCEL_CONFIG", conf),
        patch(
            "dawos_agent.services.radius.get_radius_status",
            new_callable=AsyncMock,
            return_value=mock_status,
        ),
        patch(
            "dawos_agent.services.radius._tcp_reachable",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        result = await check_radius()

    assert result["healthy"] is False  # unknown state ≠ active
    assert result["checks"][0]["state"] == "unknown"
