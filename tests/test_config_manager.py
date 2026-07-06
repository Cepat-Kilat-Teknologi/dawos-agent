"""Tests for config_manager service — uses tmp files."""

import contextlib
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from dawos_agent.services import config_manager


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temporary config setup."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text("[ppp]\nverbose=1\n")
    backup_dir = tmp_path / "accel-ppp.d"
    return conf, backup_dir


def test_read_config(tmp_config):
    conf, _ = tmp_config
    with patch.object(config_manager, "ACCEL_CONFIG", conf):
        content, mtime = config_manager.read_config()

    assert "[ppp]" in content
    assert isinstance(mtime, datetime)


def test_read_config_not_found():
    fake = Path("/nonexistent/accel-ppp.conf")
    with patch.object(config_manager, "ACCEL_CONFIG", fake), pytest.raises(
        FileNotFoundError
    ):
        config_manager.read_config()


def test_write_config_with_backup(tmp_config):
    conf, backup_dir = tmp_config
    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        backup_path = config_manager.write_config("[ppp]\nnew=1\n", backup=True)

    assert backup_path is not None
    assert backup_dir.exists()
    assert conf.read_text() == "[ppp]\nnew=1\n"
    # Backup file should contain original content
    bak_files = list(backup_dir.glob("*.bak"))
    assert len(bak_files) == 1
    assert "[ppp]\nverbose=1\n" in bak_files[0].read_text()


def test_write_config_no_backup(tmp_config):
    conf, backup_dir = tmp_config
    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        backup_path = config_manager.write_config("[ppp]\nnew=1\n", backup=False)

    assert backup_path is None
    assert not backup_dir.exists()


def test_write_config_no_existing_file(tmp_path):
    conf = tmp_path / "new.conf"
    backup_dir = tmp_path / "backups"
    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        backup_path = config_manager.write_config("[ppp]\n", backup=True)

    assert backup_path is None  # nothing to back up
    assert conf.read_text() == "[ppp]\n"


def test_list_backups_empty(tmp_path):
    backup_dir = tmp_path / "accel-ppp.d"
    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        result = config_manager.list_backups()

    assert result == []


def test_list_backups_with_files(tmp_path):
    backup_dir = tmp_path / "accel-ppp.d"
    backup_dir.mkdir()
    (backup_dir / "accel-ppp.conf.20250101_120000.bak").write_text("[old]")
    (backup_dir / "accel-ppp.conf.20250102_120000.bak").write_text("[older]")

    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        result = config_manager.list_backups()

    assert len(result) == 2
    assert result[0]["name"].endswith(".bak")
    assert "size" in result[0]
    assert "created" in result[0]
    # Should be reverse sorted (newest first)
    assert result[0]["name"] > result[1]["name"]


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


def test_diff_configs_identical():
    content = "[ppp]\nverbose=1\n"
    result = config_manager.diff_configs(content, content)
    assert result == ""


def test_diff_configs_changed():
    old = "[ppp]\nverbose=1\n"
    new = "[ppp]\nverbose=0\n"
    result = config_manager.diff_configs(old, new)
    assert "-verbose=1" in result or "- verbose=1" in result
    assert "+verbose=0" in result or "+ verbose=0" in result


def test_diff_with_backup(tmp_config):
    conf, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    bak = backup_dir / "accel-ppp.conf.20250101_120000.bak"
    bak.write_text("[ppp]\nold=1\n")

    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        result = config_manager.diff_with_backup("accel-ppp.conf.20250101_120000.bak")

    assert result["changed"] is True
    assert "old=1" in result["diff"]


def test_diff_with_backup_identical(tmp_config):
    conf, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    bak = backup_dir / "accel-ppp.conf.20250101_120000.bak"
    bak.write_text(conf.read_text())

    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        result = config_manager.diff_with_backup("accel-ppp.conf.20250101_120000.bak")

    assert result["changed"] is False


def test_diff_with_backup_not_found(tmp_config):
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
        pytest.raises(FileNotFoundError),
    ):
        config_manager.diff_with_backup("nonexistent.bak")


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def test_rollback_to(tmp_config):
    conf, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    bak = backup_dir / "accel-ppp.conf.20250101_120000.bak"
    bak.write_text("[ppp]\nrollback=1\n")

    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        safety = config_manager.rollback_to("accel-ppp.conf.20250101_120000.bak")

    # Config should now have the rolled-back content
    assert conf.read_text() == "[ppp]\nrollback=1\n"
    # A safety backup should have been created
    assert safety != ""


def test_rollback_to_not_found(tmp_config):
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
        pytest.raises(FileNotFoundError),
    ):
        config_manager.rollback_to("nonexistent.bak")


# ---------------------------------------------------------------------------
# Checkpoint / guarded apply
# ---------------------------------------------------------------------------


def test_create_checkpoint(tmp_config):
    conf, backup_dir = tmp_config
    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        cp = config_manager.create_checkpoint()

    assert cp is not None
    assert ".checkpoint" in cp
    # Checkpoint file should contain original config
    cp_path = Path(cp)
    assert cp_path.exists()
    assert cp_path.read_text() == "[ppp]\nverbose=1\n"


def test_create_checkpoint_no_config(tmp_path):
    missing = tmp_path / "nope.conf"
    with patch.object(config_manager, "ACCEL_CONFIG", missing):
        cp = config_manager.create_checkpoint()

    assert cp is None


@pytest.mark.asyncio
async def test_auto_rollback(tmp_config):
    conf, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Create checkpoint
    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        config_manager.create_checkpoint()
        # Overwrite config
        conf.write_text("[ppp]\nnew=1\n")
        # Run auto-rollback with 0-second delay
        await config_manager._auto_rollback(0)

    # Config should be restored
    assert conf.read_text() == "[ppp]\nverbose=1\n"


@pytest.mark.asyncio
async def test_auto_rollback_cancelled(tmp_config):
    import asyncio

    conf, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        config_manager.create_checkpoint()
        conf.write_text("[ppp]\nnew=1\n")

        # Start timer and cancel it
        config_manager.start_guarded_timer(300)
        config_manager.cancel_guarded_timer()

        # Give event loop a tick
        await asyncio.sleep(0)

    # Config should NOT be rolled back
    assert conf.read_text() == "[ppp]\nnew=1\n"


def test_guarded_apply_status_no_pending():
    # Reset module state
    config_manager._rollback_task = None
    config_manager._checkpoint_path = None

    status = config_manager.guarded_apply_status()
    assert status["pending"] is False
    assert status["checkpoint"] is None


def test_cancel_guarded_timer_idempotent():
    """cancel_guarded_timer should be safe to call with no active timer."""
    config_manager._rollback_task = None
    config_manager._checkpoint_path = None
    config_manager.cancel_guarded_timer()  # should not raise
    assert config_manager._rollback_task is None


@pytest.mark.asyncio
async def test_auto_rollback_cancelled_error():
    """Cover the CancelledError handler in _auto_rollback."""
    import asyncio

    async def cancel_soon(task):
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # Set up checkpoint state
    config_manager._checkpoint_path = Path("/tmp/fake.checkpoint")
    task = asyncio.get_event_loop().create_task(
        config_manager._auto_rollback(9999),
    )
    await cancel_soon(task)
    # CancelledError path was hit — task is done
    assert task.done()
