"""accel-ppp configuration file management.

Provides CRUD operations for the accel-ppp configuration file, including
reading, writing with automatic backup, unified diff generation, and
rollback to previous revisions.

Includes a guarded-apply workflow: create a checkpoint before applying
changes, then either confirm within a timeout window or let the system
automatically roll back to the checkpoint.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import shutil
from datetime import datetime
from pathlib import Path

from ..config import ACCEL_CONFIG, BACKUP_DIR

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module state — guarded apply timer
# ---------------------------------------------------------------------------

_rollback_task: asyncio.Task | None = None  # pylint: disable=invalid-name
_checkpoint_path: Path | None = None  # pylint: disable=invalid-name


# ---------------------------------------------------------------------------
# Core CRUD
# ---------------------------------------------------------------------------


def read_config() -> tuple[str, datetime | None]:
    """Read the current accel-ppp configuration file.

    Returns:
        A tuple of (file_content, last_modified_datetime).

    Raises:
        FileNotFoundError: If the configuration file does not exist.
    """
    if not ACCEL_CONFIG.exists():
        raise FileNotFoundError(f"Config file not found: {ACCEL_CONFIG}")

    content = ACCEL_CONFIG.read_text(encoding="utf-8")
    stat = ACCEL_CONFIG.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime)

    return content, mtime


def write_config(content: str, *, backup: bool = True) -> str | None:
    """Write new content to the accel-ppp configuration file.

    Optionally creates a timestamped backup of the current file before
    overwriting.

    Args:
        content: The full configuration text to write.
        backup: If ``True``, back up the existing file first.

    Returns:
        The backup file path if a backup was created, otherwise ``None``.

    Raises:
        ValueError: If *content* is empty or does not look like a valid
            accel-ppp configuration file.
    """
    stripped = content.strip()
    if not stripped:
        raise ValueError("Refusing to write empty configuration — would destroy config")
    if "[" not in stripped:
        raise ValueError(
            "Configuration must contain at least one section header (e.g. [modules])"
        )
    backup_path = None

    if backup and ACCEL_CONFIG.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"accel-ppp.conf.{ts}.bak"
        shutil.copy2(ACCEL_CONFIG, backup_file)
        backup_path = str(backup_file)
        log.info("Config backed up to %s", backup_path)

    ACCEL_CONFIG.write_text(content, encoding="utf-8")
    log.info("Config written to %s (%d bytes)", ACCEL_CONFIG, len(content))

    return backup_path


def list_backups() -> list[dict]:
    """List all available configuration backups.

    Returns:
        A list of dicts, each containing ``path``, ``name``, ``size``,
        and ``created`` for one backup file, sorted newest first.
    """
    if not BACKUP_DIR.exists():
        return []

    backups = []
    for f in sorted(BACKUP_DIR.glob("accel-ppp.conf.*"), reverse=True):
        if f.suffix not in {".bak", ".checkpoint"}:
            continue
        stat = f.stat()
        backups.append(
            {
                "path": str(f),
                "name": f.name,
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )

    return backups


def read_backup(backup_name: str) -> tuple[str, int, str]:
    """Read the content of a specific backup or checkpoint file.

    Args:
        backup_name: Filename of the backup to read.

    Returns:
        A tuple of (content, size_bytes, created_iso).

    Raises:
        FileNotFoundError: If the named backup does not exist.
    """
    bak_path = BACKUP_DIR / backup_name
    if not bak_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_name}")

    content = bak_path.read_text(encoding="utf-8")
    stat = bak_path.stat()
    created = datetime.fromtimestamp(stat.st_mtime).isoformat()
    return content, stat.st_size, created


def diff_two_revisions(name_a: str, name_b: str) -> dict:
    """Compute a unified diff between two backup revisions.

    Unlike :func:`diff_with_backup` which always compares against the
    running config, this function compares any two named revisions
    directly.

    Args:
        name_a: Filename of the first (older) revision.
        name_b: Filename of the second (newer) revision.

    Returns:
        A dictionary with ``from_name``, ``to_name``, ``diff``
        (unified diff text), and ``changed`` (bool).

    Raises:
        FileNotFoundError: If either revision does not exist.
    """
    path_a = BACKUP_DIR / name_a
    path_b = BACKUP_DIR / name_b
    if not path_a.exists():
        raise FileNotFoundError(f"Revision not found: {name_a}")
    if not path_b.exists():
        raise FileNotFoundError(f"Revision not found: {name_b}")

    content_a = path_a.read_text(encoding="utf-8")
    content_b = path_b.read_text(encoding="utf-8")
    raw_diff = diff_configs(content_a, content_b)
    return {
        "from_name": name_a,
        "to_name": name_b,
        "diff": raw_diff,
        "changed": len(raw_diff) > 0,
    }


# ---------------------------------------------------------------------------
# Diff — compare two config revisions
# ---------------------------------------------------------------------------


def diff_configs(old_content: str, new_content: str) -> str:
    """Generate a unified diff between two configuration strings.

    Args:
        old_content: The previous configuration text.
        new_content: The current configuration text.

    Returns:
        A unified-diff formatted string.  Empty if no differences.
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="previous",
        tofile="current",
        lineterm="",
    )
    return "".join(diff)


def diff_with_backup(backup_name: str) -> dict:
    """Compare the active configuration against a named backup.

    Args:
        backup_name: Filename of the backup to compare against.

    Returns:
        A dictionary with ``diff`` (unified diff text) and ``changed``
        (boolean indicating whether differences exist).

    Raises:
        FileNotFoundError: If the named backup does not exist.
    """
    bak_path = BACKUP_DIR / backup_name
    if not bak_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_name}")

    current, _ = read_config()
    old = bak_path.read_text(encoding="utf-8")
    raw_diff = diff_configs(old, current)
    return {"diff": raw_diff, "changed": len(raw_diff) > 0}


# ---------------------------------------------------------------------------
# Rollback — restore a backup and optionally reload accel-ppp
# ---------------------------------------------------------------------------


def rollback_to(backup_name: str) -> str:
    """Restore a previous configuration backup as the active config.

    Creates a safety backup of the current configuration before
    overwriting, so the rollback itself can be undone if needed.

    Args:
        backup_name: Filename of the backup to restore.

    Returns:
        The path of the safety backup that was created.

    Raises:
        FileNotFoundError: If the named backup does not exist.
    """
    bak_path = BACKUP_DIR / backup_name
    if not bak_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_name}")

    # Safety net: back up current before rollback
    safety_backup = write_config(
        bak_path.read_text(encoding="utf-8"),
        backup=True,
    )
    log.info(
        "Rolled back config from %s (safety backup: %s)", backup_name, safety_backup
    )
    return safety_backup or ""


# ---------------------------------------------------------------------------
# Guarded apply — checkpoint + auto-rollback timer
# ---------------------------------------------------------------------------


def create_checkpoint() -> str | None:
    """Snapshot the current configuration before a guarded apply.

    The checkpoint is saved alongside regular backups and is used by
    the auto-rollback timer if the apply is not confirmed in time.

    Returns:
        The checkpoint file path, or ``None`` if no config file exists.
    """
    global _checkpoint_path  # noqa: PLW0603  # pylint: disable=global-statement
    if not ACCEL_CONFIG.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cp_file = BACKUP_DIR / f"accel-ppp.conf.{ts}.checkpoint"
    shutil.copy2(ACCEL_CONFIG, cp_file)
    _checkpoint_path = cp_file
    log.info("Checkpoint created: %s", cp_file)
    return str(cp_file)


async def _auto_rollback(seconds: int) -> None:
    """Wait *seconds*, then restore the checkpoint if not confirmed.

    This coroutine is spawned as a background task by
    :func:`start_guarded_timer`.  If it completes without being
    cancelled, the active configuration is overwritten with the
    checkpoint contents.

    Args:
        seconds: Number of seconds to wait before rolling back.
    """
    try:
        await asyncio.sleep(seconds)
        if _checkpoint_path and _checkpoint_path.exists():
            content = _checkpoint_path.read_text(encoding="utf-8")
            ACCEL_CONFIG.write_text(content, encoding="utf-8")
            log.warning(
                "Auto-rollback triggered after %ds — config restored from %s",
                seconds,
                _checkpoint_path,
            )
    except asyncio.CancelledError:
        log.info("Auto-rollback cancelled (config confirmed)")


def start_guarded_timer(seconds: int = 300) -> None:
    """Start the auto-rollback countdown timer.

    If :func:`cancel_guarded_timer` is not called before *seconds*
    elapse, the configuration is automatically restored from the
    last checkpoint.

    Args:
        seconds: Timeout in seconds (default 300 — five minutes).
    """
    global _rollback_task  # noqa: PLW0603  # pylint: disable=global-statement
    cancel_guarded_timer()
    loop = asyncio.get_event_loop()
    _rollback_task = loop.create_task(_auto_rollback(seconds))
    log.info("Guarded timer started: %ds", seconds)


def cancel_guarded_timer() -> None:
    """Cancel the pending auto-rollback timer, confirming the apply.

    After this call, the current configuration is considered accepted
    and no automatic rollback will occur.
    """
    global _rollback_task, _checkpoint_path  # noqa: PLW0603  # pylint: disable=global-statement
    if _rollback_task and not _rollback_task.done():
        _rollback_task.cancel()
        log.info("Guarded timer cancelled")
    _rollback_task = None
    _checkpoint_path = None


def guarded_apply_status() -> dict:
    """Return the current guarded-apply state.

    Returns:
        A dictionary with ``pending`` (bool) and ``checkpoint`` (path
        string or ``None``).
    """
    pending = _rollback_task is not None and not _rollback_task.done()
    return {
        "pending": pending,
        "checkpoint": str(_checkpoint_path) if _checkpoint_path else None,
    }
