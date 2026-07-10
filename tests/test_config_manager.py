"""Tests for config_manager service — uses tmp files."""

import contextlib
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

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
    with (
        patch.object(config_manager, "ACCEL_CONFIG", fake),
        pytest.raises(FileNotFoundError),
    ):
        config_manager.read_config()


def test_read_backup_valid_and_rejects_traversal(tmp_config):
    """read_backup serves flat backups but rejects traversal names (DA-H01)."""
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    good = backup_dir / "accel-ppp.conf.20260101.bak"
    good.write_text("[ppp]\nverbose=1\n")
    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        content, size, _ = config_manager.read_backup(good.name)
        assert "[ppp]" in content
        assert size > 0
        for bad in ("../accel-ppp.conf", "../../etc/passwd", "..", "sub/x.bak"):
            with pytest.raises(FileNotFoundError):
                config_manager.read_backup(bad)


def test_diff_and_rollback_reject_traversal(tmp_config):
    """diff/compare/rollback must reject path-traversal names (DA-H01)."""
    conf, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        with pytest.raises(FileNotFoundError):
            config_manager.diff_with_backup("../../etc/passwd")
        with pytest.raises(FileNotFoundError):
            config_manager.diff_two_revisions("..", "x")
        with pytest.raises(FileNotFoundError):
            config_manager.rollback_to("../../etc/passwd")


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


def test_list_backups_skips_non_matching_suffix(tmp_path):
    """Files with suffixes other than .bak/.checkpoint are ignored."""
    backup_dir = tmp_path / "accel-ppp.d"
    backup_dir.mkdir()
    (backup_dir / "accel-ppp.conf.20250101_120000.bak").write_text("[ok]")
    (backup_dir / "accel-ppp.conf.20250101_120000.tmp").write_text("[skip]")
    (backup_dir / "accel-ppp.conf.20250102_120000.checkpoint").write_text("[ok2]")

    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        result = config_manager.list_backups()

    names = [r["name"] for r in result]
    assert len(result) == 2
    assert any(n.endswith(".bak") for n in names)
    assert any(n.endswith(".checkpoint") for n in names)
    assert not any(n.endswith(".tmp") for n in names)


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
        patch.object(config_manager.accel, "reload_config", new_callable=AsyncMock),
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


def test_write_config_rejects_empty_content(tmp_config):
    """write_config must refuse empty content to prevent config destruction."""
    conf, backup_dir = tmp_config
    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
        pytest.raises(ValueError, match="empty"),
    ):
        config_manager.write_config("", backup=False)


def test_write_config_rejects_no_section_header(tmp_config):
    """write_config must refuse content without INI section headers."""
    conf, backup_dir = tmp_config
    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
        pytest.raises(ValueError, match="section header"),
    ):
        config_manager.write_config("just some random text", backup=False)


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


# ---------------------------------------------------------------------------
# read_backup
# ---------------------------------------------------------------------------


def test_read_backup(tmp_config):
    conf, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    bak = backup_dir / "accel-ppp.conf.20250101_120000.bak"
    bak.write_text("[ppp]\nverbose=1\n")

    with (
        patch.object(config_manager, "ACCEL_CONFIG", conf),
        patch.object(config_manager, "BACKUP_DIR", backup_dir),
    ):
        content, size, created = config_manager.read_backup(bak.name)

    assert "[ppp]" in content
    assert size > 0
    assert created  # non-empty ISO string


def test_read_backup_not_found(tmp_config):
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)

    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        with pytest.raises(FileNotFoundError, match="not found"):
            config_manager.read_backup("nonexistent.bak")


def test_read_backup_checkpoint(tmp_config):
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    cp = backup_dir / "accel-ppp.conf.20250102_080000.checkpoint"
    cp.write_text("[modules]\nlog_syslog\n")

    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        content, size, _ = config_manager.read_backup(cp.name)

    assert "[modules]" in content
    assert size > 0


# ---------------------------------------------------------------------------
# diff_two_revisions
# ---------------------------------------------------------------------------


def test_diff_two_revisions(tmp_config):
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    a = backup_dir / "a.bak"
    b = backup_dir / "b.bak"
    a.write_text("[ppp]\nverbose=0\n")
    b.write_text("[ppp]\nverbose=1\n")

    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        result = config_manager.diff_two_revisions("a.bak", "b.bak")

    assert result["from_name"] == "a.bak"
    assert result["to_name"] == "b.bak"
    assert result["changed"] is True
    assert "verbose" in result["diff"]


def test_diff_two_revisions_identical(tmp_config):
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    a = backup_dir / "a.bak"
    b = backup_dir / "b.bak"
    a.write_text("[ppp]\nverbose=1\n")
    b.write_text("[ppp]\nverbose=1\n")

    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        result = config_manager.diff_two_revisions("a.bak", "b.bak")

    assert result["changed"] is False
    assert result["diff"] == ""


def test_diff_two_revisions_first_not_found(tmp_config):
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    b = backup_dir / "b.bak"
    b.write_text("[ppp]\n")

    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        with pytest.raises(FileNotFoundError, match="missing.bak"):
            config_manager.diff_two_revisions("missing.bak", "b.bak")


def test_diff_two_revisions_second_not_found(tmp_config):
    _, backup_dir = tmp_config
    backup_dir.mkdir(parents=True, exist_ok=True)
    a = backup_dir / "a.bak"
    a.write_text("[ppp]\n")

    with patch.object(config_manager, "BACKUP_DIR", backup_dir):
        with pytest.raises(FileNotFoundError, match="missing.bak"):
            config_manager.diff_two_revisions("a.bak", "missing.bak")
