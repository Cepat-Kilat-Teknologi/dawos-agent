"""Tests for accel-cmd parsers (pure functions, no subprocess needed)."""

from dawos_agent.services.accel import parse_ippool, parse_stat, parse_table


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
