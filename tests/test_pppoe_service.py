"""Tests for services/pppoe.py — PPPoE interface config parsing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from dawos_agent.services import pppoe

# ---------------------------------------------------------------------------
# Sample config
# ---------------------------------------------------------------------------

SAMPLE_CONFIG = """\
[modules]
log_file
pppoe
auth_mschap_v2
radius
shaper

[core]
log-error=/var/log/accel-ppp/core.log
thread-count=4

[pppoe]
interface=eth0.100
interface=eth0.200,padi-limit=0
verbose=1

[dns]
dns1=8.8.8.8
dns2=8.8.4.4

[ip-pool]
gw=10.0.0.1
10.0.0.2-10.0.0.254,name=pool1
"""

SAMPLE_CONFIG_NO_IFACE = """\
[modules]
pppoe

[pppoe]
verbose=1

[dns]
dns1=8.8.8.8
"""

SAMPLE_CONFIG_PPPOE_LAST = """\
[modules]
pppoe

[pppoe]
interface=eth0.100
verbose=1
"""


# ---------------------------------------------------------------------------
# _parse_pppoe_interfaces
# ---------------------------------------------------------------------------


def test_parse_interfaces():
    result = pppoe._parse_pppoe_interfaces(SAMPLE_CONFIG)
    assert len(result) == 2
    assert result[0].name == "eth0.100"
    assert result[0].options == ""
    assert result[1].name == "eth0.200"
    assert result[1].options == "padi-limit=0"


def test_parse_no_interfaces():
    result = pppoe._parse_pppoe_interfaces(SAMPLE_CONFIG_NO_IFACE)
    assert len(result) == 0


def test_parse_empty_config():
    result = pppoe._parse_pppoe_interfaces("")
    assert result == []


def test_parse_no_pppoe_section():
    config = "[modules]\npppoe\n\n[dns]\ndns1=8.8.8.8\n"
    result = pppoe._parse_pppoe_interfaces(config)
    assert result == []


# ---------------------------------------------------------------------------
# _rebuild_config
# ---------------------------------------------------------------------------


def test_rebuild_preserves_non_pppoe():
    from dawos_agent.models.schemas import PppoeInterface

    ifaces = [PppoeInterface(name="eth0.300", options="padi-limit=5")]
    result = pppoe._rebuild_config(SAMPLE_CONFIG, ifaces)

    # Non-pppoe sections should be preserved
    assert "[modules]" in result
    assert "log_file" in result
    assert "[dns]" in result
    assert "dns1=8.8.8.8" in result
    assert "[ip-pool]" in result

    # Old interface lines should be replaced
    assert "interface=eth0.100" not in result
    assert "interface=eth0.200" not in result

    # New interface line should be present
    assert "interface=eth0.300,padi-limit=5" in result

    # Other [pppoe] settings preserved
    assert "verbose=1" in result


def test_rebuild_empty_interfaces():

    result = pppoe._rebuild_config(SAMPLE_CONFIG, [])

    # No interface= lines at all
    assert "interface=" not in result
    assert "verbose=1" in result


def test_rebuild_pppoe_last_section():
    from dawos_agent.models.schemas import PppoeInterface

    ifaces = [PppoeInterface(name="eth0.500")]
    result = pppoe._rebuild_config(SAMPLE_CONFIG_PPPOE_LAST, ifaces)

    assert "interface=eth0.500" in result
    assert "interface=eth0.100" not in result


def test_rebuild_no_existing_interfaces():
    from dawos_agent.models.schemas import PppoeInterface

    ifaces = [PppoeInterface(name="eth0.100")]
    result = pppoe._rebuild_config(SAMPLE_CONFIG_NO_IFACE, ifaces)

    assert "interface=eth0.100" in result
    assert "verbose=1" in result


def test_rebuild_no_existing_interfaces_with_options():
    """Cover line 83: flush with options when leaving [pppoe] with no prior interface= lines."""
    from dawos_agent.models.schemas import PppoeInterface

    ifaces = [PppoeInterface(name="eth0.100", options="padi-limit=0")]
    result = pppoe._rebuild_config(SAMPLE_CONFIG_NO_IFACE, ifaces)

    assert "interface=eth0.100,padi-limit=0" in result
    assert "verbose=1" in result


def test_rebuild_pppoe_last_no_interfaces():
    """Cover lines 108-112: [pppoe] is last section and has no interface= lines."""
    from dawos_agent.models.schemas import PppoeInterface

    config = "[modules]\npppoe\n\n[pppoe]\nverbose=1\n"
    ifaces = [PppoeInterface(name="eth0.300", options="padi-limit=5")]
    result = pppoe._rebuild_config(config, ifaces)

    assert "interface=eth0.300,padi-limit=5" in result
    assert "verbose=1" in result


# ---------------------------------------------------------------------------
# list_pppoe_interfaces
# ---------------------------------------------------------------------------


def test_list_pppoe_interfaces(tmp_path):
    config = tmp_path / "accel-ppp.conf"
    config.write_text(SAMPLE_CONFIG)

    result = pppoe.list_pppoe_interfaces(config_path=config)
    assert len(result) == 2
    assert result[0].name == "eth0.100"


def test_list_pppoe_interfaces_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        pppoe.list_pppoe_interfaces(config_path=tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# add_pppoe_interface
# ---------------------------------------------------------------------------


def test_add_pppoe_interface(tmp_path):
    config = tmp_path / "accel-ppp.conf"
    config.write_text(SAMPLE_CONFIG)

    # Mock write_config to write to our temp file instead
    with patch("dawos_agent.services.pppoe.config_manager.write_config") as mock_write:
        mock_write.side_effect = lambda content, **kw: config.write_text(content)
        msg = pppoe.add_pppoe_interface("eth0.300", config_path=config)

    assert "Added" in msg
    assert "eth0.300" in msg

    # Verify config was updated
    new_content = config.read_text()
    assert "interface=eth0.300" in new_content
    # Original interfaces preserved
    assert "interface=eth0.100" in new_content
    assert "interface=eth0.200,padi-limit=0" in new_content


def test_add_pppoe_interface_with_options(tmp_path):
    config = tmp_path / "accel-ppp.conf"
    config.write_text(SAMPLE_CONFIG)

    with patch("dawos_agent.services.pppoe.config_manager.write_config") as mock_write:
        mock_write.side_effect = lambda content, **kw: config.write_text(content)
        msg = pppoe.add_pppoe_interface(
            "eth0.300",
            options="padi-limit=10",
            config_path=config,
        )

    assert "Added" in msg
    new_content = config.read_text()
    assert "interface=eth0.300,padi-limit=10" in new_content


def test_add_pppoe_interface_duplicate(tmp_path):
    config = tmp_path / "accel-ppp.conf"
    config.write_text(SAMPLE_CONFIG)

    with pytest.raises(ValueError, match="already exists"):
        pppoe.add_pppoe_interface("eth0.100", config_path=config)


def test_add_pppoe_interface_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        pppoe.add_pppoe_interface("eth0.100", config_path=tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# remove_pppoe_interface
# ---------------------------------------------------------------------------


def test_remove_pppoe_interface(tmp_path):
    config = tmp_path / "accel-ppp.conf"
    config.write_text(SAMPLE_CONFIG)

    with patch("dawos_agent.services.pppoe.config_manager.write_config") as mock_write:
        mock_write.side_effect = lambda content, **kw: config.write_text(content)
        msg = pppoe.remove_pppoe_interface("eth0.100", config_path=config)

    assert "Removed" in msg
    assert "eth0.100" in msg

    new_content = config.read_text()
    assert "interface=eth0.100" not in new_content
    # Other interface still present
    assert "interface=eth0.200,padi-limit=0" in new_content


def test_remove_pppoe_interface_not_found_in_section(tmp_path):
    config = tmp_path / "accel-ppp.conf"
    config.write_text(SAMPLE_CONFIG)

    with pytest.raises(ValueError, match="not found"):
        pppoe.remove_pppoe_interface("eth0.999", config_path=config)


def test_remove_pppoe_interface_config_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        pppoe.remove_pppoe_interface("eth0.100", config_path=tmp_path / "nonexistent")
