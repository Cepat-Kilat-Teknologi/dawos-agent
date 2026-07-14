"""Tests for services/session_history.py — SQLite session snapshots."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import session_history


@pytest.fixture()
def db_file(tmp_path):
    """Return a fresh SQLite database path in a temp directory."""
    return tmp_path / "test-history.db"


# ---------------------------------------------------------------------------
# _init_db / _connect
# ---------------------------------------------------------------------------


def test_init_db_creates_file(db_file):
    """_init_db creates the database file and table."""
    session_history._init_db(db_file)
    assert db_file.exists()


def test_init_db_creates_parent_dirs(tmp_path):
    """_init_db creates parent directories if they don't exist."""
    deep = tmp_path / "a" / "b" / "c" / "history.db"
    session_history._init_db(deep)
    assert deep.exists()


def test_init_db_idempotent(db_file):
    """_init_db can be called multiple times without error."""
    session_history._init_db(db_file)
    session_history._init_db(db_file)
    assert db_file.exists()


# ---------------------------------------------------------------------------
# _insert_snapshot
# ---------------------------------------------------------------------------


def test_insert_snapshot(db_file):
    """_insert_snapshot inserts session rows and returns count."""
    sessions = [
        {
            "username": "user1",
            "ip": "10.0.0.1",
            "sid": "abc123",
            "ifname": "ppp0",
            "calling-sid": "AA:BB:CC:DD:EE:FF",
            "state": "active",
            "uptime": "01:00:00",
            "rx-bytes": "1000",
            "tx-bytes": "2000",
        },
        {
            "username": "user2",
            "ip": "10.0.0.2",
            "sid": "def456",
            "ifname": "ppp1",
            "calling-sid": "11:22:33:44:55:66",
            "state": "active",
            "uptime": "00:30:00",
            "rx-bytes": "500",
            "tx-bytes": "800",
        },
    ]
    count = session_history._insert_snapshot(db_file, sessions, "2026-01-01T00:00:00")
    assert count == 2


def test_insert_snapshot_empty(db_file):
    """_insert_snapshot with no sessions inserts zero rows."""
    count = session_history._insert_snapshot(db_file, [], "2026-01-01T00:00:00")
    assert count == 0


def test_insert_snapshot_missing_fields(db_file):
    """_insert_snapshot handles sessions with missing fields gracefully."""
    sessions = [{"username": "partial"}]
    count = session_history._insert_snapshot(db_file, sessions, "2026-01-01T00:00:00")
    assert count == 1


# ---------------------------------------------------------------------------
# snapshot_sessions (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_sessions(db_file):
    """snapshot_sessions captures live sessions into the database."""
    mock_sessions = [
        {
            "username": "user1",
            "ip": "10.0.0.1",
            "sid": "s1",
            "ifname": "ppp0",
            "calling-sid": "AA:BB:CC:DD:EE:FF",
            "state": "active",
            "uptime": "01:00:00",
            "rx-bytes": "1000",
            "tx-bytes": "2000",
        },
    ]
    with patch.object(
        session_history.accel,
        "show_sessions",
        AsyncMock(return_value=mock_sessions),
    ):
        result = await session_history.snapshot_sessions(db_path=db_file)

    assert result["success"] is True
    assert result["captured"] == 1
    assert result["snapshot_at"] != ""


@pytest.mark.asyncio
async def test_snapshot_sessions_empty(db_file):
    """snapshot_sessions with no active sessions captures zero."""
    with patch.object(
        session_history.accel,
        "show_sessions",
        AsyncMock(return_value=[]),
    ):
        result = await session_history.snapshot_sessions(db_path=db_file)

    assert result["captured"] == 0


# ---------------------------------------------------------------------------
# _query_rows / query_history
# ---------------------------------------------------------------------------


def _seed_db(db_file):
    """Insert test data for query tests."""
    sessions_a = [
        {"username": "alice", "ip": "10.0.0.1", "sid": "s1"},
        {"username": "bob", "ip": "10.0.0.2", "sid": "s2"},
    ]
    sessions_b = [
        {"username": "alice", "ip": "10.0.0.1", "sid": "s3"},
        {"username": "carol", "ip": "10.0.0.3", "sid": "s4"},
    ]
    session_history._insert_snapshot(db_file, sessions_a, "2026-01-01T00:00:00")
    session_history._insert_snapshot(db_file, sessions_b, "2026-01-02T00:00:00")


def test_query_rows_all(db_file):
    """_query_rows without filters returns all records."""
    _seed_db(db_file)
    records, total = session_history._query_rows(db_file)
    assert total == 4
    assert len(records) == 4


def test_query_rows_by_username(db_file):
    """_query_rows filters by username."""
    _seed_db(db_file)
    records, total = session_history._query_rows(db_file, username="alice")
    assert total == 2
    assert all(r["username"] == "alice" for r in records)


def test_query_rows_by_ip(db_file):
    """_query_rows filters by IP address."""
    _seed_db(db_file)
    records, total = session_history._query_rows(db_file, ip="10.0.0.2")
    assert total == 1
    assert records[0]["username"] == "bob"


def test_query_rows_by_time_range(db_file):
    """_query_rows filters by start/end timestamps."""
    _seed_db(db_file)
    records, total = session_history._query_rows(
        db_file, start="2026-01-01T12:00:00", end="2026-01-02T12:00:00"
    )
    assert total == 2  # only the Jan 2 snapshot


def test_query_rows_pagination(db_file):
    """_query_rows supports limit and offset."""
    _seed_db(db_file)
    records, total = session_history._query_rows(db_file, limit=2, offset=0)
    assert total == 4
    assert len(records) == 2

    records2, _ = session_history._query_rows(db_file, limit=2, offset=2)
    assert len(records2) == 2


def test_query_rows_empty_db(db_file):
    """_query_rows on empty database returns zero."""
    records, total = session_history._query_rows(db_file)
    assert total == 0
    assert records == []


@pytest.mark.asyncio
async def test_query_history(db_file):
    """query_history returns paginated results."""
    _seed_db(db_file)
    result = await session_history.query_history(
        username="alice", limit=10, db_path=db_file
    )
    assert result["total"] == 2
    assert len(result["records"]) == 2
    assert result["limit"] == 10
    assert result["offset"] == 0


@pytest.mark.asyncio
async def test_query_history_clamps_limit(db_file):
    """query_history clamps limit to [1, 1000]."""
    _seed_db(db_file)
    result = await session_history.query_history(limit=5000, db_path=db_file)
    assert result["limit"] == 1000

    result2 = await session_history.query_history(limit=-5, db_path=db_file)
    assert result2["limit"] == 1


@pytest.mark.asyncio
async def test_query_history_clamps_offset(db_file):
    """query_history clamps offset to >= 0."""
    _seed_db(db_file)
    result = await session_history.query_history(offset=-10, db_path=db_file)
    assert result["offset"] == 0


# ---------------------------------------------------------------------------
# _purge_rows / purge_history
# ---------------------------------------------------------------------------


def test_purge_rows(db_file):
    """_purge_rows deletes records older than cutoff."""
    _seed_db(db_file)
    deleted = session_history._purge_rows(db_file, "2026-01-01T12:00:00")
    assert deleted == 2  # Jan 1 snapshot (2 rows)

    _, remaining = session_history._query_rows(db_file)
    assert remaining == 2  # Jan 2 snapshot still present


def test_purge_rows_nothing_to_delete(db_file):
    """_purge_rows with future cutoff deletes nothing."""
    _seed_db(db_file)
    deleted = session_history._purge_rows(db_file, "2020-01-01T00:00:00")
    assert deleted == 0


@pytest.mark.asyncio
async def test_purge_history(db_file):
    """purge_history deletes old records asynchronously."""
    _seed_db(db_file)
    deleted = await session_history.purge_history(
        before="2026-01-01T12:00:00", db_path=db_file
    )
    assert deleted == 2


# ---------------------------------------------------------------------------
# _get_stats / history_stats
# ---------------------------------------------------------------------------


def test_get_stats(db_file):
    """_get_stats returns aggregate statistics."""
    _seed_db(db_file)
    stats = session_history._get_stats(db_file)
    assert stats["total_records"] == 4
    assert stats["unique_users"] == 3  # alice, bob, carol
    assert stats["oldest_snapshot"] == "2026-01-01T00:00:00"
    assert stats["newest_snapshot"] == "2026-01-02T00:00:00"
    assert stats["db_size_bytes"] > 0


def test_get_stats_empty(db_file):
    """_get_stats on empty database returns zeroes."""
    stats = session_history._get_stats(db_file)
    assert stats["total_records"] == 0
    assert stats["unique_users"] == 0
    assert stats["oldest_snapshot"] == ""
    assert stats["newest_snapshot"] == ""


@pytest.mark.asyncio
async def test_history_stats(db_file):
    """history_stats returns stats asynchronously."""
    _seed_db(db_file)
    stats = await session_history.history_stats(db_path=db_file)
    assert stats["total_records"] == 4
    assert stats["unique_users"] == 3


# ---------------------------------------------------------------------------
# _db_path
# ---------------------------------------------------------------------------


def test_db_path_override():
    """_db_path returns the override when provided."""
    p = Path("/custom/path.db")
    assert session_history._db_path(p) == p


def test_db_path_default():
    """_db_path falls back to settings when no override."""
    result = session_history._db_path(None)
    assert str(result) == session_history.settings.history_db
