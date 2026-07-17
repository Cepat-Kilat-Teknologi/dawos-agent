"""Tests for services/traffic.py — throughput sampling, SSE, shaper."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import traffic

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# _safe_int / _sse
# ---------------------------------------------------------------------------


def test_safe_int_valid():
    assert traffic._safe_int("42") == 42


def test_safe_int_invalid():
    assert traffic._safe_int("abc") == 0


def test_safe_int_none():
    assert traffic._safe_int(None) == 0


def test_safe_int_default():
    assert traffic._safe_int("bad", default=-1) == -1


def test_sse_format():
    result = traffic._sse({"hello": "world"})
    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    parsed = json.loads(result[6:].strip())
    assert parsed == {"hello": "world"}


# ---------------------------------------------------------------------------
# compute_throughput (pure function)
# ---------------------------------------------------------------------------


def test_compute_throughput_normal():
    # 1_000_000 tx bytes in 1 second = 8 Mbps download
    dl, ul = traffic.compute_throughput(
        prev=(0, 0),
        curr=(500_000, 1_000_000),
        elapsed=1.0,
    )
    assert dl == 8.0
    assert ul == 4.0


def test_compute_throughput_zero_elapsed():
    dl, ul = traffic.compute_throughput((0, 0), (100, 100), 0.0)
    assert dl == 0.0
    assert ul == 0.0


def test_compute_throughput_negative_elapsed():
    dl, ul = traffic.compute_throughput((0, 0), (100, 100), -1.0)
    assert dl == 0.0
    assert ul == 0.0


def test_compute_throughput_counter_wrap():
    """Negative delta should clamp to 0."""
    dl, ul = traffic.compute_throughput((1000, 1000), (500, 500), 1.0)
    assert dl == 0.0
    assert ul == 0.0


# ---------------------------------------------------------------------------
# sample_session_bytes
# ---------------------------------------------------------------------------

SAMPLE_TABLE = """\
 rx-bytes-raw | tx-bytes-raw
--------------+--------------
 123456       | 654321
"""


@pytest.mark.asyncio
async def test_sample_session_bytes():
    with patch(
        "dawos_agent.services.traffic.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=SAMPLE_TABLE,
    ):
        result = await traffic.sample_session_bytes("user1")

    assert result == (123456, 654321)


@pytest.mark.asyncio
async def test_sample_session_bytes_no_session():
    with patch(
        "dawos_agent.services.traffic.accel.run_cmd",
        new_callable=AsyncMock,
        return_value="",
    ):
        result = await traffic.sample_session_bytes("offline_user")

    assert result is None


# ---------------------------------------------------------------------------
# sample_all_sessions
# ---------------------------------------------------------------------------

SAMPLE_ALL = """\
 sid   | username | ip       | rate-limit | rx-bytes-raw | tx-bytes-raw
-------+----------+----------+------------+--------------+--------------
 abc1  | user1    | 10.0.0.2 | 5M/20M     | 100          | 200
 abc2  | user2    | 10.0.0.3 | 10M/50M    | 300          | 400
"""


@pytest.mark.asyncio
async def test_sample_all_sessions():
    with patch(
        "dawos_agent.services.traffic.accel.run_cmd",
        new_callable=AsyncMock,
        return_value=SAMPLE_ALL,
    ):
        result = await traffic.sample_all_sessions()

    assert len(result) == 2
    assert result[0]["username"] == "user1"
    assert result[1]["sid"] == "abc2"


# ---------------------------------------------------------------------------
# user_traffic_events (SSE generator)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_traffic_events_no_session():
    with patch(
        "dawos_agent.services.traffic.sample_session_bytes",
        new_callable=AsyncMock,
        return_value=None,
    ):
        events = []
        async for ev in traffic.user_traffic_events("offline"):
            events.append(ev)

    assert len(events) == 1
    data = json.loads(events[0][6:].strip())
    assert "error" in data
    assert "no session found" in data["error"]


@pytest.mark.asyncio
async def test_user_traffic_events_session_ends():
    call_count = 0

    async def mock_sample(username):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return (100, 200)  # initial sample
        if call_count == 2:
            return (200, 400)  # second sample
        return None  # session ended

    with (
        patch(
            "dawos_agent.services.traffic.sample_session_bytes",
            side_effect=mock_sample,
        ),
        patch("dawos_agent.services.traffic.asyncio.sleep", new_callable=AsyncMock),
    ):
        events = []
        async for ev in traffic.user_traffic_events("user1", interval=1.0):
            events.append(ev)

    assert len(events) == 2  # one data event + one "session ended"
    data = json.loads(events[0][6:].strip())
    assert "download_mbps" in data
    ended = json.loads(events[1][6:].strip())
    assert "session ended" in ended["error"]


# ---------------------------------------------------------------------------
# aggregate_traffic_events (SSE generator)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_traffic_events_no_sessions():
    with patch(
        "dawos_agent.services.traffic.sample_all_sessions",
        new_callable=AsyncMock,
        return_value=[],
    ):
        events = []
        async for ev in traffic.aggregate_traffic_events():
            events.append(ev)

    assert len(events) == 1
    data = json.loads(events[0][6:].strip())
    assert "no active sessions" in data["error"]


@pytest.mark.asyncio
async def test_aggregate_traffic_events_produces_data():
    call_count = 0

    async def mock_all():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return [
                {
                    "sid": "s1",
                    "username": "u1",
                    "ip": "10.0.0.2",
                    "rate-limit": "5M/20M",
                    "rx-bytes-raw": str(call_count * 100),
                    "tx-bytes-raw": str(call_count * 200),
                },
            ]
        return []  # sessions gone

    with (
        patch(
            "dawos_agent.services.traffic.sample_all_sessions",
            side_effect=mock_all,
        ),
        patch("dawos_agent.services.traffic.asyncio.sleep", new_callable=AsyncMock),
    ):
        events = []
        async for ev in traffic.aggregate_traffic_events(interval=1.0):
            events.append(ev)

    assert len(events) == 2  # one data + one "no active sessions"
    data = json.loads(events[0][6:].strip())
    assert "sessions" in data
    assert data["session_count"] == 1


# ---------------------------------------------------------------------------
# get_queue_stats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_queue_stats():
    with (
        patch(
            "dawos_agent.services.traffic.accel.ifname_of",
            new_callable=AsyncMock,
            return_value="ppp0",
        ),
        patch(
            "dawos_agent.services.traffic._tc",
            new_callable=AsyncMock,
            return_value="qdisc fq_codel",
        ),
    ):
        result = await traffic.get_queue_stats("user1")

    assert result["ifname"] == "ppp0"
    assert result["username"] == "user1"
    assert "fq_codel" in result["qdisc"]


@pytest.mark.asyncio
async def test_get_queue_stats_no_session():
    with (
        patch(
            "dawos_agent.services.traffic.accel.ifname_of",
            new_callable=AsyncMock,
            return_value=None,
        ),
        pytest.raises(ValueError, match="No live session"),
    ):
        await traffic.get_queue_stats("offline")


# ---------------------------------------------------------------------------
# change_ratelimit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_change_ratelimit_with_slash():
    with (
        patch(
            "dawos_agent.services.traffic.accel.ifname_of",
            new_callable=AsyncMock,
            return_value="ppp0",
        ),
        patch(
            "dawos_agent.services.traffic.accel.shaper_change",
            new_callable=AsyncMock,
        ) as mock_shaper,
    ):
        msg = await traffic.change_ratelimit("user1", "5M/20M")

    # up/down → down/up for accel-cmd
    mock_shaper.assert_called_once_with("ppp0", "20M/5M")
    assert "user1" in msg


@pytest.mark.asyncio
async def test_change_ratelimit_no_slash():
    with (
        patch(
            "dawos_agent.services.traffic.accel.ifname_of",
            new_callable=AsyncMock,
            return_value="ppp0",
        ),
        patch(
            "dawos_agent.services.traffic.accel.shaper_change",
            new_callable=AsyncMock,
        ) as mock_shaper,
    ):
        await traffic.change_ratelimit("user1", "10M")

    mock_shaper.assert_called_once_with("ppp0", "10M")


@pytest.mark.asyncio
async def test_change_ratelimit_no_session():
    with (
        patch(
            "dawos_agent.services.traffic.accel.ifname_of",
            new_callable=AsyncMock,
            return_value=None,
        ),
        pytest.raises(ValueError, match="No live session"),
    ):
        await traffic.change_ratelimit("offline", "5M/20M")


# ---------------------------------------------------------------------------
# restore_ratelimit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_ratelimit():
    with (
        patch(
            "dawos_agent.services.traffic.accel.ifname_of",
            new_callable=AsyncMock,
            return_value="ppp0",
        ),
        patch(
            "dawos_agent.services.traffic.accel.shaper_restore",
            new_callable=AsyncMock,
        ),
    ):
        msg = await traffic.restore_ratelimit("user1")

    assert "restored" in msg.lower()


@pytest.mark.asyncio
async def test_restore_ratelimit_no_session():
    with (
        patch(
            "dawos_agent.services.traffic.accel.ifname_of",
            new_callable=AsyncMock,
            return_value=None,
        ),
        pytest.raises(ValueError, match="No live session"),
    ):
        await traffic.restore_ratelimit("offline")


# ---------------------------------------------------------------------------
# _tc helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tc_helper():
    proc = _mock_proc("qdisc fq_codel 0: root")
    with patch(
        "dawos_agent.services.traffic.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await traffic._tc("tc -s qdisc show dev ppp0")

    assert "fq_codel" in result
