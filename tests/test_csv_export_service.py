"""Tests for services/csv_export.py — CSV export service."""

from __future__ import annotations

import csv
import io
from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import csv_export

# ---------------------------------------------------------------------------
# _sanitize
# ---------------------------------------------------------------------------


def test_sanitize_normal():
    """Normal values pass through unchanged."""
    assert csv_export._sanitize("hello") == "hello"
    assert csv_export._sanitize("10.0.0.1") == "10.0.0.1"
    assert csv_export._sanitize("") == ""


def test_sanitize_formula_equals():
    """Values starting with = are prefixed."""
    assert csv_export._sanitize("=SUM(A1)") == "'=SUM(A1)"


def test_sanitize_formula_plus():
    """Values starting with + are prefixed."""
    assert csv_export._sanitize("+cmd") == "'+cmd"


def test_sanitize_formula_minus():
    """Values starting with - are prefixed."""
    assert csv_export._sanitize("-1+1") == "'-1+1"


def test_sanitize_formula_at():
    """Values starting with @ are prefixed."""
    assert csv_export._sanitize("@import") == "'@import"


def test_sanitize_formula_tab():
    """Values starting with tab are prefixed."""
    assert csv_export._sanitize("\tcmd") == "'\tcmd"


def test_sanitize_formula_cr():
    """Values starting with carriage return are prefixed."""
    assert csv_export._sanitize("\rcmd") == "'\rcmd"


# ---------------------------------------------------------------------------
# _rows_to_csv
# ---------------------------------------------------------------------------


def test_rows_to_csv_basic():
    """Renders header + data rows as quoted CSV."""
    fields = ("name", "ip")
    rows = [{"name": "alice", "ip": "10.0.0.1"}]
    result = csv_export._rows_to_csv(fields, rows)
    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert lines[0] == ["name", "ip"]
    assert lines[1] == ["alice", "10.0.0.1"]


def test_rows_to_csv_empty():
    """Empty row list produces header-only CSV."""
    fields = ("a", "b")
    result = csv_export._rows_to_csv(fields, [])
    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert len(lines) == 1
    assert lines[0] == ["a", "b"]


def test_rows_to_csv_missing_field():
    """Missing fields in row dict default to empty string."""
    fields = ("name", "ip", "extra")
    rows = [{"name": "bob"}]
    result = csv_export._rows_to_csv(fields, rows)
    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert lines[1] == ["bob", "", ""]


def test_rows_to_csv_sanitizes():
    """Formula-injection characters are sanitized in output."""
    fields = ("val",)
    rows = [{"val": "=EVIL"}]
    result = csv_export._rows_to_csv(fields, rows)
    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert lines[1] == ["'=EVIL"]


# ---------------------------------------------------------------------------
# export_sessions_csv (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_sessions_csv():
    """export_sessions_csv returns CSV with session data."""
    mock_sessions = [
        {
            "ifname": "ppp0",
            "username": "user1",
            "ip": "10.0.0.1",
            "calling-sid": "AA:BB:CC:DD:EE:FF",
            "rate-limit": "10M/50M",
            "type": "pppoe",
            "state": "active",
            "uptime": "01:00:00",
            "rx-bytes": "1000",
            "tx-bytes": "2000",
        },
    ]
    with patch.object(
        csv_export.accel,
        "show_sessions",
        AsyncMock(return_value=mock_sessions),
    ):
        result = await csv_export.export_sessions_csv()

    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert len(lines) == 2  # header + 1 row
    assert lines[0][0] == "ifname"
    assert lines[1][1] == "user1"


@pytest.mark.asyncio
async def test_export_sessions_csv_empty():
    """export_sessions_csv with no sessions returns header only."""
    with patch.object(
        csv_export.accel,
        "show_sessions",
        AsyncMock(return_value=[]),
    ):
        result = await csv_export.export_sessions_csv()

    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert len(lines) == 1  # header only


# ---------------------------------------------------------------------------
# export_history_csv (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_history_csv(tmp_path):
    """export_history_csv returns CSV with history records."""
    from dawos_agent.services import session_history

    db = tmp_path / "test.db"
    sessions = [
        {"username": "alice", "ip": "10.0.0.1", "sid": "s1"},
        {"username": "bob", "ip": "10.0.0.2", "sid": "s2"},
    ]
    session_history._insert_snapshot(db, sessions, "2026-01-01T00:00:00")

    result = await csv_export.export_history_csv(db_path=db)
    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert len(lines) == 3  # header + 2 rows
    assert lines[0][0] == "id"
    assert lines[0][1] == "snapshot_at"


@pytest.mark.asyncio
async def test_export_history_csv_with_filters(tmp_path):
    """export_history_csv respects username filter."""
    from dawos_agent.services import session_history

    db = tmp_path / "test.db"
    sessions = [
        {"username": "alice", "ip": "10.0.0.1"},
        {"username": "bob", "ip": "10.0.0.2"},
    ]
    session_history._insert_snapshot(db, sessions, "2026-01-01T00:00:00")

    result = await csv_export.export_history_csv(username="alice", db_path=db)
    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert len(lines) == 2  # header + 1 alice row


@pytest.mark.asyncio
async def test_export_history_csv_empty(tmp_path):
    """export_history_csv on empty DB returns header only."""
    db = tmp_path / "test.db"
    result = await csv_export.export_history_csv(db_path=db)
    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert len(lines) == 1  # header only


@pytest.mark.asyncio
async def test_export_history_csv_clamps_limit(tmp_path):
    """export_history_csv clamps limit to [1, 50000]."""
    from dawos_agent.services import session_history

    db = tmp_path / "test.db"
    sessions = [{"username": "u1"}]
    session_history._insert_snapshot(db, sessions, "2026-01-01T00:00:00")

    # Limit too high — clamped to 50000 (still works)
    result = await csv_export.export_history_csv(limit=99999, db_path=db)
    reader = csv.reader(io.StringIO(result))
    lines = list(reader)
    assert len(lines) == 2  # header + 1 row
