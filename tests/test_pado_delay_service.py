"""Tests for services/pado_delay.py — PADO timing control."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from dawos_agent.services import pado_delay

SAMPLE_CONFIG = """\
[pppoe]
interface=eth0.100
pado-delay=500
pado-delay-sessions=100
"""


@pytest.fixture()
def config_file(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text(SAMPLE_CONFIG)
    return p


# ---------------------------------------------------------------------------
# get_pado_delay
# ---------------------------------------------------------------------------


def test_get_pado_delay(config_file):
    result = pado_delay.get_pado_delay(config_path=config_file)
    assert result["delay"] == 500
    assert result["min_sessions"] == 100
    assert "500ms" in result["description"]


def test_get_pado_delay_none(tmp_path):
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0\n")
    result = pado_delay.get_pado_delay(config_path=p)
    assert result["delay"] == 0
    assert "No PADO delay" in result["description"]


def test_get_pado_delay_skips_non_pppoe(tmp_path):
    """Cover the 'not in_pppoe: continue' branch."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[other]\nfoo=bar\n[pppoe]\npado-delay=100\n")
    result = pado_delay.get_pado_delay(config_path=p)
    assert result["delay"] == 100


def test_get_pado_delay_missing():
    with pytest.raises(FileNotFoundError):
        pado_delay.get_pado_delay(config_path=Path("/nonexistent"))


# ---------------------------------------------------------------------------
# set_pado_delay
# ---------------------------------------------------------------------------


def test_set_pado_delay_update(config_file):
    written = {}

    def capture(content, **_kw):
        written["content"] = content

    with patch.object(pado_delay.config_manager, "write_config", side_effect=capture):
        result = pado_delay.set_pado_delay(
            1000, min_sessions=200, config_path=config_file
        )

    assert "1000ms" in result
    assert "pado-delay=1000" in written["content"]
    assert "pado-delay-sessions=200" in written["content"]


def test_set_pado_delay_insert(tmp_path):
    """Cover injection when no pado-delay exists, with sessions on section transition."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0\n[other]\nfoo=bar\n")

    written = {}

    def capture(content, **_kw):
        written["content"] = content

    with patch.object(pado_delay.config_manager, "write_config", side_effect=capture):
        pado_delay.set_pado_delay(250, min_sessions=10, config_path=p)

    assert "pado-delay=250" in written["content"]
    assert "pado-delay-sessions=10" in written["content"]


def test_set_pado_delay_at_eof(tmp_path):
    """Cover [pppoe] as last section."""
    p = tmp_path / "accel-ppp.conf"
    p.write_text("[pppoe]\ninterface=eth0\n")

    written = {}

    def capture(content, **_kw):
        written["content"] = content

    with patch.object(pado_delay.config_manager, "write_config", side_effect=capture):
        pado_delay.set_pado_delay(300, min_sessions=50, config_path=p)

    assert "pado-delay=300" in written["content"]
    assert "pado-delay-sessions=50" in written["content"]


def test_set_pado_delay_negative():
    with pytest.raises(ValueError, match="negative"):
        pado_delay.set_pado_delay(-1)


def test_set_pado_delay_missing():
    with pytest.raises(FileNotFoundError):
        pado_delay.set_pado_delay(100, config_path=Path("/nonexistent"))


def test_set_pado_delay_zero_sessions(config_file):
    """Cover the branch where min_sessions=0 skips pado-delay-sessions."""
    written = {}

    def capture(content, **_kw):
        written["content"] = content

    with patch.object(pado_delay.config_manager, "write_config", side_effect=capture):
        pado_delay.set_pado_delay(100, min_sessions=0, config_path=config_file)

    assert "pado-delay=100" in written["content"]
    # pado-delay-sessions should be removed (skipped) when min_sessions=0
    assert "pado-delay-sessions" not in written["content"]
