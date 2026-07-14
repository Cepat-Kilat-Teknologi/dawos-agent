"""Tests for PPPoE runtime configuration service — pure functions."""

from __future__ import annotations

import pytest

from dawos_agent.services.pppoe_config import (
    _parse_pppoe_runtime,
    get_pppoe_runtime_config,
    set_pppoe_runtime_config,
)

# ---------------------------------------------------------------------------
# _parse_pppoe_runtime
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = """\
[modules]
radius

[pppoe]
interface=ens19
service-name=internet
ac-name=bng-jakarta-1
verbose=1
pado-delay=500

[radius]
server=10.0.0.1,secret
"""


def test_parse_pppoe_runtime_full():
    """All three runtime keys are extracted correctly."""
    result = _parse_pppoe_runtime(SAMPLE_CONFIG)
    assert result["service_name"] == "internet"
    assert result["ac_name"] == "bng-jakarta-1"
    assert result["verbose"] == 1


def test_parse_pppoe_runtime_defaults():
    """Missing keys produce safe defaults."""
    text = "[pppoe]\ninterface=ens19\n"
    result = _parse_pppoe_runtime(text)
    assert result["service_name"] == ""
    assert result["ac_name"] == ""
    assert result["verbose"] == 0


def test_parse_pppoe_runtime_empty():
    """Empty config string produces defaults."""
    result = _parse_pppoe_runtime("")
    assert result["service_name"] == ""
    assert result["ac_name"] == ""
    assert result["verbose"] == 0


def test_parse_pppoe_runtime_no_pppoe_section():
    """Config without [pppoe] section produces defaults."""
    text = "[radius]\nnas-identifier=test\n"
    result = _parse_pppoe_runtime(text)
    assert result["service_name"] == ""
    assert result["verbose"] == 0


def test_parse_pppoe_runtime_comments_ignored():
    """Comment lines within [pppoe] are skipped."""
    text = """\
[pppoe]
# service-name=should-not-appear
service-name=real-service
#verbose=1
"""
    result = _parse_pppoe_runtime(text)
    assert result["service_name"] == "real-service"
    assert result["verbose"] == 0


def test_parse_pppoe_runtime_non_numeric_verbose():
    """Non-numeric verbose value uses default 0."""
    text = "[pppoe]\nverbose=yes\n"
    result = _parse_pppoe_runtime(text)
    assert result["verbose"] == 0


def test_parse_pppoe_runtime_other_section_keys_ignored():
    """Keys from other sections don't bleed into PPPoE result."""
    text = """\
[pppoe]
service-name=pppoe-svc
[radius]
service-name=radius-should-not-appear
"""
    result = _parse_pppoe_runtime(text)
    assert result["service_name"] == "pppoe-svc"


def test_parse_pppoe_runtime_blank_lines_ignored():
    """Blank lines within [pppoe] are harmless."""
    text = """\
[pppoe]

service-name=test

ac-name=ac1

"""
    result = _parse_pppoe_runtime(text)
    assert result["service_name"] == "test"
    assert result["ac_name"] == "ac1"


def test_parse_pppoe_runtime_no_equals_lines_ignored():
    """Lines without = inside [pppoe] are skipped."""
    text = "[pppoe]\nsome-directive\nservice-name=ok\n"
    result = _parse_pppoe_runtime(text)
    assert result["service_name"] == "ok"


# ---------------------------------------------------------------------------
# get_pppoe_runtime_config
# ---------------------------------------------------------------------------


def test_get_pppoe_runtime_config_reads_file(tmp_path):
    """get_pppoe_runtime_config() reads and parses the config."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[pppoe]\nservice-name=myisp\nac-name=bng1\nverbose=1\n",
        encoding="utf-8",
    )
    result = get_pppoe_runtime_config(config_path=conf)
    assert result["service_name"] == "myisp"
    assert result["ac_name"] == "bng1"
    assert result["verbose"] == 1


def test_get_pppoe_runtime_config_file_not_found():
    """get_pppoe_runtime_config() raises FileNotFoundError for missing file."""
    from pathlib import Path

    missing = Path("/nonexistent/accel-ppp.conf")
    with pytest.raises(FileNotFoundError):
        get_pppoe_runtime_config(config_path=missing)


# ---------------------------------------------------------------------------
# set_pppoe_runtime_config
# ---------------------------------------------------------------------------


def test_set_pppoe_runtime_config_all_keys(tmp_path):
    """set_pppoe_runtime_config() updates all three keys."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[pppoe]\ninterface=ens19\nservice-name=old\nac-name=old\nverbose=0\n",
        encoding="utf-8",
    )

    from unittest.mock import patch

    with patch(
        "dawos_agent.services.pppoe_config.config_manager.write_config"
    ) as mock_write:
        result = set_pppoe_runtime_config(
            service_name="new-svc",
            ac_name="new-ac",
            verbose=1,
            config_path=conf,
        )
        # Verify write_config was called with updated content
        written = mock_write.call_args[0][0]
        assert "service-name=new-svc" in written
        assert "ac-name=new-ac" in written
        assert "verbose=1" in written
        # Original interface line preserved
        assert "interface=ens19" in written

    assert "new-svc" in result
    assert "new-ac" in result


def test_set_pppoe_runtime_config_partial_update(tmp_path):
    """set_pppoe_runtime_config() updates only specified keys."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[pppoe]\nservice-name=keep\nac-name=old-ac\nverbose=0\n",
        encoding="utf-8",
    )

    from unittest.mock import patch

    with patch(
        "dawos_agent.services.pppoe_config.config_manager.write_config"
    ) as mock_write:
        set_pppoe_runtime_config(
            ac_name="new-ac",
            config_path=conf,
        )
        written = mock_write.call_args[0][0]
        # Only ac-name changed; service-name and verbose untouched
        assert "service-name=keep" in written
        assert "ac-name=new-ac" in written
        assert "verbose=0" in written


def test_set_pppoe_runtime_config_adds_missing_keys(tmp_path):
    """set_pppoe_runtime_config() appends keys not in config yet."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text("[pppoe]\ninterface=ens19\n", encoding="utf-8")

    from unittest.mock import patch

    with patch(
        "dawos_agent.services.pppoe_config.config_manager.write_config"
    ) as mock_write:
        set_pppoe_runtime_config(
            service_name="new-svc",
            config_path=conf,
        )
        written = mock_write.call_args[0][0]
        assert "service-name=new-svc" in written
        assert "interface=ens19" in written


def test_set_pppoe_runtime_config_pppoe_at_eof(tmp_path):
    """set_pppoe_runtime_config() handles [pppoe] as last section."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[radius]\nnas-identifier=test\n[pppoe]\ninterface=ens19\n",
        encoding="utf-8",
    )

    from unittest.mock import patch

    with patch(
        "dawos_agent.services.pppoe_config.config_manager.write_config"
    ) as mock_write:
        set_pppoe_runtime_config(
            verbose=1,
            config_path=conf,
        )
        written = mock_write.call_args[0][0]
        assert "verbose=1" in written
        assert "[radius]" in written


def test_set_pppoe_runtime_config_file_not_found():
    """set_pppoe_runtime_config() raises FileNotFoundError for missing file."""
    from pathlib import Path

    missing = Path("/nonexistent/accel-ppp.conf")
    with pytest.raises(FileNotFoundError):
        set_pppoe_runtime_config(
            service_name="test",
            config_path=missing,
        )


def test_set_pppoe_runtime_config_no_fields():
    """set_pppoe_runtime_config() raises ValueError when nothing to update."""
    with pytest.raises(ValueError, match="At least one field"):
        set_pppoe_runtime_config()


def test_set_pppoe_runtime_config_preserves_other_sections(tmp_path):
    """set_pppoe_runtime_config() does not corrupt other sections."""
    conf = tmp_path / "accel-ppp.conf"
    conf.write_text(
        "[modules]\nradius\n\n[pppoe]\nverbose=0\n\n[radius]\ntimeout=5\n",
        encoding="utf-8",
    )

    from unittest.mock import patch

    with patch(
        "dawos_agent.services.pppoe_config.config_manager.write_config"
    ) as mock_write:
        set_pppoe_runtime_config(verbose=1, config_path=conf)
        written = mock_write.call_args[0][0]
        assert "[modules]" in written
        assert "[radius]" in written
        assert "timeout=5" in written
        assert "verbose=1" in written


def test_set_pppoe_runtime_config_appends_at_section_boundary(tmp_path):
    """Missing key is appended before the next section header."""
    conf = tmp_path / "accel-ppp.conf"
    # [pppoe] has no service-name; [radius] follows immediately
    conf.write_text(
        "[pppoe]\ninterface=ens19\n[radius]\ntimeout=5\n",
        encoding="utf-8",
    )

    from unittest.mock import patch

    with patch(
        "dawos_agent.services.pppoe_config.config_manager.write_config"
    ) as mock_write:
        set_pppoe_runtime_config(service_name="new-svc", config_path=conf)
        written = mock_write.call_args[0][0]
        # service-name must appear BEFORE [radius], not after it
        svc_pos = written.index("service-name=new-svc")
        rad_pos = written.index("[radius]")
        assert svc_pos < rad_pos
        assert "interface=ens19" in written
