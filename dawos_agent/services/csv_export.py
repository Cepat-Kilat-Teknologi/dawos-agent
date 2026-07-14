"""CSV export service — generate CSV from sessions and history.

Produces RFC 4180-compliant CSV output from live PPPoE sessions
(via ``accel-cmd show sessions``) and from the SQLite session history
database.  All values are quoted to prevent formula injection in
spreadsheet applications (security hardening).
"""

from __future__ import annotations

import csv
import io
import logging

from . import accel, session_history

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

_SESSION_FIELDS = (
    "ifname",
    "username",
    "ip",
    "calling-sid",
    "rate-limit",
    "type",
    "state",
    "uptime",
    "rx-bytes",
    "tx-bytes",
)

_HISTORY_FIELDS = (
    "id",
    "snapshot_at",
    "username",
    "ip",
    "sid",
    "ifname",
    "calling_sid",
    "state",
    "uptime",
    "rx_bytes",
    "tx_bytes",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize(value: str) -> str:
    """Strip leading formula-injection characters from a cell value.

    Spreadsheet applications (Excel, LibreOffice Calc) interpret leading
    ``=``, ``+``, ``-``, ``@``, ``\\t``, ``\\r`` as formula markers.
    Prefixing with a single-quote neutralises the trigger without
    altering the data for non-spreadsheet consumers.

    Args:
        value: Raw cell value.

    Returns:
        Sanitised string safe for CSV embedding.
    """
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return value


def _rows_to_csv(
    fields: tuple[str, ...],
    rows: list[dict[str, str]],
) -> str:
    """Render a list of row dicts as a CSV string.

    Args:
        fields: Ordered tuple of column names for the header row.
        rows: List of dicts, each keyed by field name.

    Returns:
        A complete CSV document as a string (with trailing newline).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(fields)
    for row in rows:
        writer.writerow(_sanitize(str(row.get(f, ""))) for f in fields)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def export_sessions_csv() -> str:
    """Export all active PPPoE sessions as CSV.

    Fetches live session data from ``accel-cmd show sessions`` and
    formats it as a downloadable CSV document.

    Returns:
        CSV string with header row and one row per active session.
    """
    columns = ",".join(_SESSION_FIELDS)
    sessions = await accel.show_sessions(columns=columns)
    log.info("CSV export: %d active sessions", len(sessions))
    return _rows_to_csv(_SESSION_FIELDS, sessions)


async def export_history_csv(
    *,
    username: str | None = None,
    ip: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 10000,
    db_path=None,
) -> str:
    """Export session history records as CSV.

    Queries the SQLite history database with optional filters and
    formats matching records as a downloadable CSV document.

    Args:
        username: Optional exact username filter.
        ip: Optional exact IP address filter.
        start: Optional ISO-8601 lower bound for snapshot_at.
        end: Optional ISO-8601 upper bound for snapshot_at.
        limit: Maximum records to export (default 10 000, max 50 000).
        db_path: Override database path (for testing).

    Returns:
        CSV string with header row and one row per history record.
    """
    clamped = max(1, min(limit, 50000))
    result = await session_history.query_history(
        username=username,
        ip=ip,
        start=start,
        end=end,
        limit=clamped,
        offset=0,
        db_path=db_path,
    )
    records = result["records"]
    log.info("CSV export: %d history records", len(records))
    return _rows_to_csv(_HISTORY_FIELDS, records)
