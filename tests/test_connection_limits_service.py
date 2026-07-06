"""Tests for services/connection_limits.py — session/rate caps."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from dawos_agent.services import connection_limits

SAMPLE_CONFIG = """\
[modules]
log_file

[pppoe]
interface=eth0.100
max-sessions=500
max-starting=50

[common]
session-timeout=3600
"""


@pytest.fixture()
def config_file(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text(SAMPLE_CONFIG)
    return p


# ---------------------------------------------------------------------------
# get_limits
# ---------------------------------------------------------------------------


def test_get_limits(config_file):
    result = connection_limits.get_limits(config_path=config_file)
    assert result["max_sessions"] == 500
    assert result["max_starting"] == 50
    assert result["session_timeout"] == 3600


def test_get_limits_missing():
    from pathlib import Path

    with pytest.raises(FileNotFoundError):
        connection_limits.get_limits(config_path=Path("/nonexistent"))


def test_get_limits_no_values(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0\n")
    result = connection_limits.get_limits(config_path=p)
    assert result["max_sessions"] == 0
    assert result["max_starting"] == 0


# ---------------------------------------------------------------------------
# set_limits
# ---------------------------------------------------------------------------


def test_set_limits(config_file):
    with patch.object(connection_limits.config_manager, "write_config"):
        result = connection_limits.set_limits(
            max_sessions=1000,
            max_starting=100,
            config_path=config_file,
        )
    assert "updated" in result.lower()


def test_set_limits_insert_new(tmp_path):
    """Cover injection of missing keys into [pppoe]."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0\n[other]\nfoo=bar\n")

    written = {}

    def capture_write(content, **_kw):
        written["content"] = content

    with patch.object(
        connection_limits.config_manager,
        "write_config",
        side_effect=capture_write,
    ):
        connection_limits.set_limits(
            max_sessions=200,
            config_path=p,
        )

    assert "max-sessions=200" in written["content"]


def test_set_limits_at_eof(tmp_path):
    """Cover [pppoe] as last section with no existing limits."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0\n")

    written = {}

    def capture_write(content, **_kw):
        written["content"] = content

    with patch.object(
        connection_limits.config_manager,
        "write_config",
        side_effect=capture_write,
    ):
        connection_limits.set_limits(
            max_sessions=300,
            max_starting=30,
            config_path=p,
        )

    assert "max-sessions=300" in written["content"]
    assert "max-starting=30" in written["content"]


def test_set_limits_missing():
    from pathlib import Path

    with pytest.raises(FileNotFoundError):
        connection_limits.set_limits(
            max_sessions=100,
            config_path=Path("/nonexistent"),
        )


def test_set_limits_inject_both_on_section_transition(tmp_path):
    """Cover max_starting injection when leaving [pppoe] for another section."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0\n[other]\nfoo=bar\n")

    written = {}

    def capture(content, **_kw):
        written["content"] = content

    with patch.object(
        connection_limits.config_manager,
        "write_config",
        side_effect=capture,
    ):
        connection_limits.set_limits(
            max_sessions=200,
            max_starting=20,
            config_path=p,
        )

    assert "max-sessions=200" in written["content"]
    assert "max-starting=20" in written["content"]


# ---------------------------------------------------------------------------
# get_interface_limit
# ---------------------------------------------------------------------------


def test_get_interface_limit_found(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0.100,padi-limit=50\n")
    result = connection_limits.get_interface_limit("eth0.100", config_path=p)
    assert result["found"] is True
    assert result["padi_limit"] == 50


def test_get_interface_limit_no_padi(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0.100\n")
    result = connection_limits.get_interface_limit("eth0.100", config_path=p)
    assert result["found"] is True
    assert result["padi_limit"] == 0


def test_get_interface_limit_not_found(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0.100\n")
    result = connection_limits.get_interface_limit("eth1.200", config_path=p)
    assert result["found"] is False


def test_get_interface_limit_missing():
    from pathlib import Path

    with pytest.raises(FileNotFoundError):
        connection_limits.get_interface_limit("eth0", config_path=Path("/nonexistent"))
