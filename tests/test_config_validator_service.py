"""Tests for services/config_validator.py — accel-ppp config validation."""

from __future__ import annotations

from dawos_agent.services import config_validator

# ---------------------------------------------------------------------------
# Valid config — no errors
# ---------------------------------------------------------------------------


def test_valid_config():
    """A well-formed config produces zero errors."""
    content = """\
[modules]
log_file
pppoe
auth_mschap_v2

[core]
log-error=/var/log/accel-ppp/core.log
thread-count=4

[pppoe]
interface=ens19

[ip-pool]
gw=10.0.0.1
10.0.0.2-254,pool1

[cli]
tcp=127.0.0.1:2001
"""
    result = config_validator.validate_config(content)
    assert result["valid"] is True
    assert result["errors"] == 0
    assert "modules" in result["sections"]
    assert "core" in result["sections"]
    assert "pppoe" in result["sections"]


def test_empty_config():
    """An empty string has no sections — [modules] is missing."""
    result = config_validator.validate_config("")
    assert result["valid"] is False
    assert result["errors"] >= 1
    assert any("[modules]" in i["message"] for i in result["issues"])


def test_comments_and_blanks_ignored():
    """Comments and blank lines are skipped without issues."""
    content = """\
# This is a comment

[modules]
log_file

# Another comment
[core]
thread-count=4
"""
    result = config_validator.validate_config(content)
    assert result["valid"] is True
    assert result["errors"] == 0


# ---------------------------------------------------------------------------
# Syntax checks
# ---------------------------------------------------------------------------


def test_orphan_line_before_section():
    """Lines before the first section header produce an error."""
    content = """\
orphan_key=value
[modules]
log_file
"""
    result = config_validator.validate_config(content)
    assert result["valid"] is False
    assert any("Orphan" in i["message"] for i in result["issues"])


def test_bare_key_in_modules_ok():
    """Bare keys (no =) in [modules] are valid — module names."""
    content = """\
[modules]
log_file
pppoe
"""
    result = config_validator.validate_config(content)
    # Only warning should be missing of other sections, but modules is fine
    errors = [i for i in result["issues"] if i["severity"] == "error"]
    bare_errors = [i for i in errors if "separator" in i["message"]]
    assert bare_errors == []


def test_bare_key_outside_modules_warns():
    """Bare keys in sections other than [modules]/[ip-pool] produce warnings."""
    content = """\
[modules]
log_file

[core]
some_bare_key
"""
    result = config_validator.validate_config(content)
    warnings = [i for i in result["issues"] if i["severity"] == "warning"]
    assert any("separator" in w["message"] for w in warnings)


# ---------------------------------------------------------------------------
# Required sections
# ---------------------------------------------------------------------------


def test_missing_modules_section():
    """Config without [modules] section produces an error."""
    content = """\
[core]
thread-count=4
"""
    result = config_validator.validate_config(content)
    assert result["valid"] is False
    assert any(
        "[modules]" in i["message"] and i["severity"] == "error"
        for i in result["issues"]
    )


def test_modules_present_valid():
    """Config with [modules] section passes required check."""
    content = """\
[modules]
log_file
"""
    result = config_validator.validate_config(content)
    errors = [
        i
        for i in result["issues"]
        if "Required" in i["message"] and i["severity"] == "error"
    ]
    assert errors == []


# ---------------------------------------------------------------------------
# Duplicate sections
# ---------------------------------------------------------------------------


def test_duplicate_section_warning():
    """Duplicate section headers produce a warning."""
    content = """\
[modules]
log_file

[core]
thread-count=4

[core]
log-error=/var/log/accel-ppp/core.log
"""
    result = config_validator.validate_config(content)
    warnings = [i for i in result["issues"] if i["severity"] == "warning"]
    assert any("appears 2 times" in w["message"] for w in warnings)


def test_no_duplicate_no_warning():
    """Non-duplicate sections produce no duplicate warning."""
    content = """\
[modules]
log_file

[core]
thread-count=4
"""
    result = config_validator.validate_config(content)
    dup_warnings = [i for i in result["issues"] if "appears" in i.get("message", "")]
    assert dup_warnings == []


# ---------------------------------------------------------------------------
# IP validation
# ---------------------------------------------------------------------------


def test_valid_ip_no_error():
    """Valid IP addresses produce no errors."""
    content = """\
[modules]
log_file

[radius]
server=127.0.0.1
"""
    result = config_validator.validate_config(content)
    ip_errors = [i for i in result["issues"] if "Invalid IP" in i["message"]]
    assert ip_errors == []


def test_invalid_ip_error():
    """Invalid IP addresses produce an error."""
    content = """\
[modules]
log_file

[radius]
server=999.999.999.999
"""
    result = config_validator.validate_config(content)
    assert result["valid"] is False
    assert any("Invalid IP" in i["message"] for i in result["issues"])


def test_valid_cidr_no_error():
    """Valid CIDR notation produces no errors."""
    content = """\
[modules]
log_file

[ip-pool]
gw=10.0.0.0/24
"""
    result = config_validator.validate_config(content)
    cidr_errors = [i for i in result["issues"] if "Invalid CIDR" in i["message"]]
    assert cidr_errors == []


def test_invalid_cidr_error():
    """Invalid CIDR notation produces an error."""
    content = """\
[modules]
log_file

[ip-pool]
gw=999.999.999.999/24
"""
    result = config_validator.validate_config(content)
    assert result["valid"] is False
    assert any("Invalid CIDR" in i["message"] for i in result["issues"])


def test_ip_in_comma_separated_value():
    """IP in comma-separated RADIUS server line is validated."""
    content = """\
[modules]
log_file

[radius]
server=192.168.1.1,secret,auth-port=1812
"""
    result = config_validator.validate_config(content)
    ip_errors = [i for i in result["issues"] if "Invalid IP" in i["message"]]
    assert ip_errors == []


def test_invalid_ip_in_comma_separated():
    """Invalid IP in comma-separated value produces an error."""
    content = """\
[modules]
log_file

[radius]
server=999.0.0.1,secret,auth-port=1812
"""
    result = config_validator.validate_config(content)
    assert result["valid"] is False
    assert any("Invalid IP" in i["message"] for i in result["issues"])


def test_ip_colon_port_valid():
    """IP:port format with valid IP produces no error."""
    content = """\
[modules]
log_file

[cli]
tcp=127.0.0.1:2001
"""
    result = config_validator.validate_config(content)
    ip_errors = [i for i in result["issues"] if "Invalid IP" in i["message"]]
    assert ip_errors == []


def test_ip_colon_port_invalid_ip():
    """IP:port format with invalid IP produces an error."""
    content = """\
[modules]
log_file

[cli]
tcp=999.0.0.1:2001
"""
    result = config_validator.validate_config(content)
    assert any("Invalid IP" in i["message"] for i in result["issues"])


# ---------------------------------------------------------------------------
# Port validation
# ---------------------------------------------------------------------------


def test_valid_port_no_error():
    """Valid port numbers produce no errors."""
    content = """\
[modules]
log_file

[cli]
tcp=127.0.0.1:2001
"""
    result = config_validator.validate_config(content)
    port_errors = [i for i in result["issues"] if "Port out of range" in i["message"]]
    assert port_errors == []


def test_port_zero_error():
    """Port 0 produces an error (out of range)."""
    content = """\
[modules]
log_file

[cli]
tcp=127.0.0.1:0
"""
    result = config_validator.validate_config(content)
    assert any("Port out of range" in i["message"] for i in result["issues"])


def test_port_too_high_error():
    """Port > 65535 produces an error."""
    content = """\
[modules]
log_file

[cli]
tcp=127.0.0.1:70000
"""
    result = config_validator.validate_config(content)
    assert any("Port out of range" in i["message"] for i in result["issues"])


def test_port_in_radius_subkey():
    """Port validation in RADIUS comma-separated sub-keys."""
    content = """\
[modules]
log_file

[radius]
server=10.0.0.1,secret,auth-port=99999
"""
    result = config_validator.validate_config(content)
    assert any("Port out of range" in i["message"] for i in result["issues"])


def test_valid_port_in_radius_subkey():
    """Valid port in RADIUS sub-keys produces no error."""
    content = """\
[modules]
log_file

[radius]
server=10.0.0.1,secret,auth-port=1812,acct-port=1813
"""
    result = config_validator.validate_config(content)
    port_errors = [i for i in result["issues"] if "Port out of range" in i["message"]]
    assert port_errors == []


# ---------------------------------------------------------------------------
# Empty value info
# ---------------------------------------------------------------------------


def test_empty_value_info():
    """Key with empty value produces an info issue."""
    content = """\
[modules]
log_file

[core]
log-error=
"""
    result = config_validator.validate_config(content)
    infos = [i for i in result["issues"] if i["severity"] == "info"]
    assert any("Empty value" in i["message"] for i in infos)


def test_non_empty_value_no_info():
    """Key with a value produces no empty-value info."""
    content = """\
[modules]
log_file

[core]
thread-count=4
"""
    result = config_validator.validate_config(content)
    infos = [
        i
        for i in result["issues"]
        if i["severity"] == "info" and "Empty" in i["message"]
    ]
    assert infos == []


# ---------------------------------------------------------------------------
# Response structure
# ---------------------------------------------------------------------------


def test_response_structure():
    """Validate the complete response dict structure."""
    content = """\
[modules]
log_file
"""
    result = config_validator.validate_config(content)
    assert "valid" in result
    assert "errors" in result
    assert "warnings" in result
    assert "sections" in result
    assert "issues" in result
    assert isinstance(result["sections"], list)
    assert isinstance(result["issues"], list)


def test_sections_list_ordered():
    """Sections appear in the order they are first encountered."""
    content = """\
[modules]
log_file

[pppoe]
interface=ens19

[core]
thread-count=4
"""
    result = config_validator.validate_config(content)
    assert result["sections"] == ["modules", "pppoe", "core"]


def test_truncate_long_line():
    """_truncate shortens lines over max_len."""
    assert config_validator._truncate("short") == "short"
    long = "a" * 100
    truncated = config_validator._truncate(long, max_len=60)
    assert len(truncated) == 63  # 60 + "..."
    assert truncated.endswith("...")


def test_warnings_count():
    """Warnings count reflects warning-severity issues."""
    content = """\
[modules]
log_file

[core]
bare_key_no_equals
another_bare_key
"""
    result = config_validator.validate_config(content)
    assert result["warnings"] == 2
