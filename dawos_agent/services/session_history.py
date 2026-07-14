"""Session history service — SQLite-backed session snapshots.

Captures point-in-time snapshots of active PPPoE sessions from
``accel-cmd show sessions`` and stores them in a local SQLite database.
Provides query, purge, and statistics operations for historical session
analysis.

The database path is configurable via ``DAWOS_HISTORY_DB`` (default
``/var/lib/dawos-agent/history.db``).  All SQL uses parameterised
queries to prevent injection.
"""

# pylint: disable=broad-exception-caught

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from . import accel

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL schema
# ---------------------------------------------------------------------------

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS session_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at TEXT    NOT NULL,
    username    TEXT    NOT NULL DEFAULT '',
    ip          TEXT    NOT NULL DEFAULT '',
    sid         TEXT    NOT NULL DEFAULT '',
    ifname      TEXT    NOT NULL DEFAULT '',
    calling_sid TEXT    NOT NULL DEFAULT '',
    state       TEXT    NOT NULL DEFAULT '',
    uptime      TEXT    NOT NULL DEFAULT '',
    rx_bytes    TEXT    NOT NULL DEFAULT '',
    tx_bytes    TEXT    NOT NULL DEFAULT ''
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sh_username ON session_history(username);",
    "CREATE INDEX IF NOT EXISTS idx_sh_snapshot_at ON session_history(snapshot_at);",
    "CREATE INDEX IF NOT EXISTS idx_sh_ip ON session_history(ip);",
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def _db_path(override: Path | None = None) -> Path:
    """Resolve the database file path.

    Args:
        override: Optional path for testing.  Falls back to the
            ``DAWOS_HISTORY_DB`` setting.

    Returns:
        Absolute path to the SQLite database file.
    """
    return override or Path(settings.history_db)


def _connect(db: Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys.

    Creates the parent directory if it does not exist.

    Args:
        db: Path to the database file.

    Returns:
        An open :class:`sqlite3.Connection`.
    """
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _init_db(db: Path) -> None:
    """Ensure the schema exists.

    Args:
        db: Path to the database file.
    """
    conn = _connect(db)
    try:
        conn.execute(_CREATE_TABLE)
        for idx_sql in _CREATE_INDEXES:
            conn.execute(idx_sql)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def _insert_snapshot(
    db: Path,
    sessions: list[dict[str, str]],
    snapshot_at: str,
) -> int:
    """Insert session rows into the history table.

    Args:
        db: Database path.
        sessions: List of session dicts from ``accel-cmd show sessions``.
        snapshot_at: ISO-8601 timestamp for this snapshot.

    Returns:
        Number of rows inserted.
    """
    _init_db(db)
    conn = _connect(db)
    try:
        rows = [
            (
                snapshot_at,
                s.get("username", ""),
                s.get("ip", ""),
                s.get("sid", ""),
                s.get("ifname", ""),
                s.get("calling-sid", ""),
                s.get("state", ""),
                s.get("uptime", ""),
                s.get("rx-bytes", s.get("rx_bytes", "")),
                s.get("tx-bytes", s.get("tx_bytes", "")),
            )
            for s in sessions
        ]
        conn.executemany(
            "INSERT INTO session_history "
            "(snapshot_at, username, ip, sid, ifname, calling_sid, "
            "state, uptime, rx_bytes, tx_bytes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


async def snapshot_sessions(db_path: Path | None = None) -> dict:
    """Capture a snapshot of all active sessions into the history database.

    Args:
        db_path: Override database path (for testing).

    Returns:
        A dict with ``success``, ``captured``, and ``snapshot_at``.
    """
    db = _db_path(db_path)
    now = datetime.now(timezone.utc).isoformat()
    sessions = await accel.show_sessions(
        columns="username,ip,sid,ifname,calling-sid,state,uptime,rx-bytes,tx-bytes"
    )
    count = await asyncio.to_thread(_insert_snapshot, db, sessions, now)
    log.info("Session snapshot captured: %d sessions at %s", count, now)
    return {"success": True, "captured": count, "snapshot_at": now}


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


def _query_rows(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    db: Path,
    *,
    username: str | None = None,
    ip: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Execute a filtered history query.

    Args:
        db: Database path.
        username: Optional username filter (exact match).
        ip: Optional IP address filter (exact match).
        start: Optional ISO-8601 lower bound for ``snapshot_at``.
        end: Optional ISO-8601 upper bound for ``snapshot_at``.
        limit: Maximum rows to return.
        offset: Number of rows to skip.

    Returns:
        A tuple of (list of row dicts, total matching count).
    """
    _init_db(db)
    conn = _connect(db)
    try:
        where_parts: list[str] = []
        params: list[str | int] = []

        if username:
            where_parts.append("username = ?")
            params.append(username)
        if ip:
            where_parts.append("ip = ?")
            params.append(ip)
        if start:
            where_parts.append("snapshot_at >= ?")
            params.append(start)
        if end:
            where_parts.append("snapshot_at <= ?")
            params.append(end)

        where_clause = ""
        if where_parts:
            where_clause = "WHERE " + " AND ".join(where_parts)

        # Count total matching
        count_sql = f"SELECT COUNT(*) FROM session_history {where_clause};"
        total = conn.execute(count_sql, params).fetchone()[0]

        # Fetch page
        query_sql = (
            f"SELECT * FROM session_history {where_clause} "
            f"ORDER BY snapshot_at DESC, id DESC LIMIT ? OFFSET ?;"
        )
        rows = conn.execute(query_sql, [*params, limit, offset]).fetchall()
        records = [dict(row) for row in rows]
        return records, total
    finally:
        conn.close()


async def query_history(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    username: str | None = None,
    ip: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db_path: Path | None = None,
) -> dict:
    """Query session history with optional filters.

    Args:
        username: Filter by exact username match.
        ip: Filter by exact IP address match.
        start: ISO-8601 lower bound for snapshot timestamp.
        end: ISO-8601 upper bound for snapshot timestamp.
        limit: Maximum records to return (1-1000).
        offset: Pagination offset.
        db_path: Override database path (for testing).

    Returns:
        A dict with ``records``, ``total``, ``limit``, ``offset``.
    """
    db = _db_path(db_path)
    clamped_limit = max(1, min(limit, 1000))
    clamped_offset = max(0, offset)
    records, total = await asyncio.to_thread(
        _query_rows,
        db,
        username=username,
        ip=ip,
        start=start,
        end=end,
        limit=clamped_limit,
        offset=clamped_offset,
    )
    return {
        "records": records,
        "total": total,
        "limit": clamped_limit,
        "offset": clamped_offset,
    }


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------


def _purge_rows(db: Path, before: str) -> int:
    """Delete history records older than *before*.

    Args:
        db: Database path.
        before: ISO-8601 timestamp cutoff.

    Returns:
        Number of rows deleted.
    """
    _init_db(db)
    conn = _connect(db)
    try:
        cursor = conn.execute(
            "DELETE FROM session_history WHERE snapshot_at < ?;",
            (before,),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


async def purge_history(before: str, db_path: Path | None = None) -> int:
    """Delete session history records older than *before*.

    Args:
        before: ISO-8601 timestamp cutoff — records with
            ``snapshot_at < before`` are deleted.
        db_path: Override database path (for testing).

    Returns:
        Number of rows deleted.
    """
    db = _db_path(db_path)
    deleted = await asyncio.to_thread(_purge_rows, db, before)
    log.info("Purged %d history records older than %s", deleted, before)
    return deleted


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def _get_stats(db: Path) -> dict:
    """Collect aggregate statistics from the history database.

    Args:
        db: Database path.

    Returns:
        A dict with ``total_records``, ``unique_users``,
        ``oldest_snapshot``, ``newest_snapshot``, ``db_size_bytes``.
    """
    _init_db(db)
    conn = _connect(db)
    try:
        total = conn.execute("SELECT COUNT(*) FROM session_history;").fetchone()[0]
        unique = conn.execute(
            "SELECT COUNT(DISTINCT username) FROM session_history;"
        ).fetchone()[0]
        oldest = (
            conn.execute("SELECT MIN(snapshot_at) FROM session_history;").fetchone()[0]
            or ""
        )
        newest = (
            conn.execute("SELECT MAX(snapshot_at) FROM session_history;").fetchone()[0]
            or ""
        )
        db_size = os.path.getsize(str(db)) if db.exists() else 0
        return {
            "total_records": total,
            "unique_users": unique,
            "oldest_snapshot": oldest,
            "newest_snapshot": newest,
            "db_size_bytes": db_size,
        }
    finally:
        conn.close()


async def history_stats(db_path: Path | None = None) -> dict:
    """Get aggregate statistics for the session history database.

    Args:
        db_path: Override database path (for testing).

    Returns:
        A dict suitable for constructing
        :class:`~dawos_agent.models.schemas.SessionHistoryStatsResponse`.
    """
    db = _db_path(db_path)
    return await asyncio.to_thread(_get_stats, db)
