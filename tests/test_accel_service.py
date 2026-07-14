"""Tests for accel-cmd parsers (pure functions, no subprocess needed)."""

import pytest

from dawos_agent.services.accel import (
    parse_ippool,
    parse_stat,
    parse_table,
    validate_columns,
)


def test_parse_table_basic():
    text = """\
 ifname | username | ip
--------+----------+--------
 ppp0   | user1    | 10.0.0.1
 ppp1   | user2    | 10.0.0.2
"""
    result = parse_table(text)
    assert len(result) == 2
    assert result[0]["ifname"] == "ppp0"
    assert result[0]["username"] == "user1"
    assert result[1]["ip"] == "10.0.0.2"


def test_parse_table_empty():
    assert parse_table("") == []
    assert parse_table("no sessions") == []


def test_parse_stat():
    text = """\
uptime: 1.02:03:04
cpu: 5%
mem(rss/virt): 15360/40960
core:
  mempool_allocated: 123456
sessions:
  starting: 2
  active: 50
  finishing: 1
pppoe:
  starting: 0
  active: 50
"""
    result = parse_stat(text)
    assert result["uptime"] == "1.02:03:04"
    assert result["cpu"] == "5"
    assert result["sessions"]["active"] == 50
    assert result["sessions"]["starting"] == 2
    assert result["sessions"]["finishing"] == 1


def test_parse_stat_empty():
    result = parse_stat("")
    assert result["sessions"]["active"] == 0


def test_parse_stat_with_blank_lines():
    """Blank lines in stat output should be skipped (line 119 coverage)."""
    text = """\
uptime: 2:00:00

cpu: 1%

sessions:
  active: 3

pppoe:
  active: 3
"""
    result = parse_stat(text)
    assert result["uptime"] == "2:00:00"
    assert result["cpu"] == "1"
    assert result["sessions"]["active"] == 3


def test_parse_stat_non_numeric_value():
    """A non-numeric session count must not raise; default is kept (DA-L02)."""
    text = "sessions:\n  active: -\n  starting: 2\n"
    result = parse_stat(text)
    assert result["sessions"]["active"] == 0  # int('-') fails → default kept
    assert result["sessions"]["starting"] == 2


def test_parse_ippool():
    text = """\
ippool:
  total: 1024
  used: 50
  available: 974
"""
    result = parse_ippool(text)
    assert result["total"] == "1024"
    assert result["used"] == "50"
    assert result["available"] == "974"


def test_parse_ippool_empty():
    result = parse_ippool("")
    assert result["total"] == "0"
    assert result["used"] == "0"


# ---------------------------------------------------------------------------
# validate_columns
# ---------------------------------------------------------------------------


def test_validate_columns_single():
    assert validate_columns("ifname") == "ifname"


def test_validate_columns_multiple():
    result = validate_columns("ifname,username,ip,sid")
    assert result == "ifname,username,ip,sid"


def test_validate_columns_all_known():
    """Every known column name should be accepted."""
    cols = "ifname,username,ip,calling-sid,called-sid,sid,rate-limit"
    result = validate_columns(cols)
    assert result == cols


def test_validate_columns_extended_fields():
    """Extended telemetry columns should all be valid."""
    cols = (
        "rx-bytes-raw,tx-bytes-raw,rx-pkts,tx-pkts,uptime-raw,inbound-if,service-name"
    )
    result = validate_columns(cols)
    assert result == cols


def test_validate_columns_strips_whitespace():
    result = validate_columns(" ifname , username , ip ")
    assert result == "ifname,username,ip"


def test_validate_columns_drops_unknown():
    """Unknown column names are silently dropped."""
    result = validate_columns("ifname,BOGUS,username")
    assert result == "ifname,username"


def test_validate_columns_all_unknown_raises():
    """If every column is unknown, raise ValueError."""
    with pytest.raises(ValueError, match="No valid columns"):
        validate_columns("BOGUS,INVALID")


def test_validate_columns_empty_raises():
    with pytest.raises(ValueError, match="No valid columns"):
        validate_columns("")


def test_validate_columns_preserves_order():
    """Column order should match caller's request, not a sorted set."""
    result = validate_columns("tx-bytes,username,ifname")
    assert result == "tx-bytes,username,ifname"


# ---------------------------------------------------------------------------
# parse_stat_extended
# ---------------------------------------------------------------------------

from dawos_agent.services.accel import parse_stat_extended  # noqa: E402

FULL_STAT_OUTPUT = """\
uptime: 2.12:58:33
cpu: 3%
mem(rss/virt): 7652/176260 kB
core:
  mempool_allocated: 279302
  mempool_available: 197230
  thread_count: 2
  thread_active: 1
  context_count: 18
  context_sleeping: 0
  context_pending: 0
  md_handler_count: 23
  md_handler_pending: 0
  timer_count: 18
  timer_pending: 0
sessions:
  starting: 0
  active: 9
  finishing: 0
pppoe:
  starting: 0
  active: 9
  delayed PADO: 0
  recv PADI: 21553
  drop PADI: 0
  sent PADO: 21553
  recv PADR(dup): 20041(0)
  sent PADS: 20041
  filtered: 0
radius(3, 10.100.0.253):
  state: active
  fail count: 0
  request count: 0
  queue length: 0
  auth sent: 454
  auth lost(total/5m/1m): 414/0/0
  auth avg query time(5m/1m): 0/0 ms
  acct sent: 124
  acct lost(total/5m/1m): 53/0/0
  acct avg query time(5m/1m): 0/0 ms
  interim sent: 2561
  interim lost(total/5m/1m): 64/0/0
  interim avg query time(5m/1m): 33/32 ms
"""


def test_parse_stat_extended_full():
    """Full production output parses every section correctly."""
    result = parse_stat_extended(FULL_STAT_OUTPUT)

    assert result["uptime"] == "2.12:58:33"
    assert result["cpu"] == "3"

    # Memory
    assert result["memory"]["rss_kb"] == 7652
    assert result["memory"]["virt_kb"] == 176260

    # Core
    assert result["core"]["mempool_allocated"] == 279302
    assert result["core"]["mempool_available"] == 197230
    assert result["core"]["thread_count"] == 2
    assert result["core"]["thread_active"] == 1
    assert result["core"]["context_count"] == 18
    assert result["core"]["context_sleeping"] == 0
    assert result["core"]["context_pending"] == 0
    assert result["core"]["md_handler_count"] == 23
    assert result["core"]["md_handler_pending"] == 0
    assert result["core"]["timer_count"] == 18
    assert result["core"]["timer_pending"] == 0

    # Sessions
    assert result["sessions"]["starting"] == 0
    assert result["sessions"]["active"] == 9
    assert result["sessions"]["finishing"] == 0

    # PPPoE
    assert result["pppoe"]["starting"] == 0
    assert result["pppoe"]["active"] == 9
    assert result["pppoe"]["delayed_pado"] == 0
    assert result["pppoe"]["recv_padi"] == 21553
    assert result["pppoe"]["drop_padi"] == 0
    assert result["pppoe"]["sent_pado"] == 21553
    assert result["pppoe"]["recv_padr"] == 20041
    assert result["pppoe"]["recv_padr_dup"] == 0
    assert result["pppoe"]["sent_pads"] == 20041
    assert result["pppoe"]["filtered"] == 0

    # RADIUS
    assert len(result["radius"]) == 1
    rad = result["radius"][0]
    assert rad["server_id"] == "3"
    assert rad["server_address"] == "10.100.0.253"
    assert rad["state"] == "active"
    assert rad["fail_count"] == 0
    assert rad["request_count"] == 0
    assert rad["queue_length"] == 0
    assert rad["auth_sent"] == 454
    assert rad["auth_lost_total"] == 414
    assert rad["auth_lost_5m"] == 0
    assert rad["auth_lost_1m"] == 0
    assert rad["auth_avg_query_time_5m"] == 0
    assert rad["auth_avg_query_time_1m"] == 0
    assert rad["acct_sent"] == 124
    assert rad["acct_lost_total"] == 53
    assert rad["acct_lost_5m"] == 0
    assert rad["acct_lost_1m"] == 0
    assert rad["acct_avg_query_time_5m"] == 0
    assert rad["acct_avg_query_time_1m"] == 0
    assert rad["interim_sent"] == 2561
    assert rad["interim_lost_total"] == 64
    assert rad["interim_lost_5m"] == 0
    assert rad["interim_lost_1m"] == 0
    assert rad["interim_avg_query_time_5m"] == 33
    assert rad["interim_avg_query_time_1m"] == 32


def test_parse_stat_extended_empty():
    """Empty input produces safe defaults."""
    result = parse_stat_extended("")
    assert result["uptime"] == ""
    assert result["cpu"] == "0"
    assert result["memory"]["rss_kb"] == 0
    assert result["memory"]["virt_kb"] == 0
    assert result["core"] == {}
    assert result["sessions"]["active"] == 0
    assert result["pppoe"] == {}
    assert result["radius"] == []


def test_parse_stat_extended_blank_lines():
    """Blank lines between sections are skipped safely."""
    text = """\
uptime: 1:00:00

cpu: 5%

mem(rss/virt): 1024/2048 kB

sessions:
  active: 3

"""
    result = parse_stat_extended(text)
    assert result["uptime"] == "1:00:00"
    assert result["cpu"] == "5"
    assert result["memory"]["rss_kb"] == 1024
    assert result["memory"]["virt_kb"] == 2048
    assert result["sessions"]["active"] == 3


def test_parse_stat_extended_multiple_radius():
    """Multiple RADIUS server blocks are parsed independently."""
    text = """\
uptime: 0:30:00
cpu: 0%
radius(1, 10.0.0.1):
  state: active
  auth sent: 100
  acct sent: 50
  interim sent: 200
radius(2, 10.0.0.2):
  state: down
  fail count: 5
  auth sent: 0
  acct sent: 0
  interim sent: 0
"""
    result = parse_stat_extended(text)
    assert len(result["radius"]) == 2

    rad1 = result["radius"][0]
    assert rad1["server_id"] == "1"
    assert rad1["server_address"] == "10.0.0.1"
    assert rad1["state"] == "active"
    assert rad1["auth_sent"] == 100

    rad2 = result["radius"][1]
    assert rad2["server_id"] == "2"
    assert rad2["server_address"] == "10.0.0.2"
    assert rad2["state"] == "down"
    assert rad2["fail_count"] == 5


def test_parse_stat_extended_no_radius():
    """Output without RADIUS section produces empty radius list."""
    text = """\
uptime: 0:05:00
cpu: 1%
mem(rss/virt): 512/1024 kB
sessions:
  active: 0
  starting: 0
  finishing: 0
"""
    result = parse_stat_extended(text)
    assert result["radius"] == []
    assert result["sessions"]["active"] == 0


def test_parse_stat_extended_non_numeric_core():
    """Non-numeric core values are silently skipped."""
    text = """\
uptime: 0:01:00
cpu: 0%
core:
  mempool_allocated: -
  thread_count: 2
"""
    result = parse_stat_extended(text)
    assert "mempool_allocated" not in result["core"]
    assert result["core"]["thread_count"] == 2


def test_parse_stat_extended_padr_without_dup():
    """recv PADR value without dup parentheses parses correctly."""
    text = """\
pppoe:
  recv PADR(dup): 500
"""
    result = parse_stat_extended(text)
    assert result["pppoe"]["recv_padr"] == 500


def test_parse_stat_extended_sessions_non_numeric():
    """Non-numeric session count uses default 0."""
    text = """\
sessions:
  active: -
  starting: 1
"""
    result = parse_stat_extended(text)
    assert result["sessions"]["active"] == 0
    assert result["sessions"]["starting"] == 1


def test_parse_stat_extended_mem_malformed():
    """Malformed mem line does not crash; defaults kept."""
    text = "mem(rss/virt): garbage\n"
    result = parse_stat_extended(text)
    assert result["memory"]["rss_kb"] == 0
    assert result["memory"]["virt_kb"] == 0


def test_parse_stat_extended_unknown_top_level():
    """Unknown top-level line (not a section) resets section to None."""
    text = """\
some random line
sessions:
  active: 5
"""
    result = parse_stat_extended(text)
    assert result["sessions"]["active"] == 5


def test_parse_stat_extended_indented_no_colon():
    """Indented line without colon is skipped."""
    text = """\
core:
  some_value_without_colon
  thread_count: 4
"""
    result = parse_stat_extended(text)
    assert result["core"]["thread_count"] == 4


def test_parse_stat_extended_radius_lost_partial():
    """Partial lost values (fewer than 3 parts) are handled."""
    text = """\
radius(1, 10.0.0.1):
  auth lost(total/5m/1m): 10/5
  auth sent: 100
"""
    result = parse_stat_extended(text)
    rad = result["radius"][0]
    # Only 2 parts → skip (needs exactly 3)
    assert "auth_lost_total" not in rad
    assert rad["auth_sent"] == 100


def test_parse_stat_extended_radius_avg_partial():
    """Partial avg query time (fewer than 2 parts) is handled."""
    text = """\
radius(1, 10.0.0.1):
  auth avg query time(5m/1m): 5
  acct avg query time(5m/1m): 10/20 ms
"""
    result = parse_stat_extended(text)
    rad = result["radius"][0]
    # Only 1 part → skip
    assert "auth_avg_query_time_5m" not in rad
    assert rad["acct_avg_query_time_5m"] == 10
    assert rad["acct_avg_query_time_1m"] == 20


# ---------------------------------------------------------------------------
# show_stat_extended (async wrapper)
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, patch  # noqa: E402

from dawos_agent.services.accel import show_stat_extended  # noqa: E402


@pytest.mark.asyncio
async def test_show_stat_extended_calls_run_cmd():
    """show_stat_extended() delegates to run_cmd and parses output."""
    mock_output = "uptime: 0:10:00\ncpu: 2%\nsessions:\n  active: 5\n"
    with patch(
        "dawos_agent.services.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=mock_output,
    ) as mock_cmd:
        result = await show_stat_extended()

    mock_cmd.assert_awaited_once_with("show stat")
    assert result["uptime"] == "0:10:00"
    assert result["cpu"] == "2"
    assert result["sessions"]["active"] == 5


# ---------------------------------------------------------------------------
# validate_match_field + search_sessions (P0.3)
# ---------------------------------------------------------------------------

from dawos_agent.services.accel import (  # noqa: E402
    search_sessions,
    validate_match_field,
)


def test_validate_match_field_valid():
    """All expected match fields are accepted."""
    for field in ("ifname", "username", "ip", "calling-sid", "sid", "state"):
        assert validate_match_field(field) == field


def test_validate_match_field_invalid():
    """Unknown field raises ValueError."""
    with pytest.raises(ValueError, match="Invalid match field"):
        validate_match_field("BOGUS")


def test_validate_match_field_column_not_matchable():
    """Valid column but not a matchable field raises ValueError."""
    # rx-bytes is a valid session column but not in SEARCH_MATCH_FIELDS
    with pytest.raises(ValueError, match="Invalid match field"):
        validate_match_field("rx-bytes")


@pytest.mark.asyncio
async def test_search_sessions_delegates():
    """search_sessions() builds correct accel-cmd and parses output."""
    table = " ifname | username\n------+--------\n ppp0 | user1\n"
    with patch(
        "dawos_agent.services.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=table,
    ) as mock_cmd:
        result = await search_sessions("calling-sid", "AA:BB:CC:DD:EE:FF")

    assert len(result) == 1
    assert result[0]["username"] == "user1"
    call_arg = mock_cmd.call_args[0][0]
    assert "match calling-sid" in call_arg
    assert "AA:BB:CC:DD:EE:FF" in call_arg


@pytest.mark.asyncio
async def test_search_sessions_invalid_field():
    """search_sessions() rejects invalid match field."""
    with pytest.raises(ValueError, match="Invalid match field"):
        await search_sessions("BOGUS", "value")


@pytest.mark.asyncio
async def test_search_sessions_custom_columns():
    """search_sessions() passes validated columns to accel-cmd."""
    table = " ifname | sid\n------+-----\n ppp0 | abc\n"
    with patch(
        "dawos_agent.services.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=table,
    ) as mock_cmd:
        result = await search_sessions("sid", "abc", columns="ifname,sid")

    assert len(result) == 1
    call_arg = mock_cmd.call_args[0][0]
    assert "ifname,sid" in call_arg
