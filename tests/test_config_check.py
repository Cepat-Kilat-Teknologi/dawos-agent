"""Tests for the configuration completeness check."""

from __future__ import annotations

import logging

from dawos_agent import config as config_module
from dawos_agent.config import check_config, settings


def test_warns_on_default_api_key(caplog):
    """Default API key should trigger a warning."""
    original = settings.api_key
    try:
        settings.api_key = "changeme-generate-a-strong-key"
        with caplog.at_level(logging.WARNING):
            msgs = check_config(logger=logging.getLogger("test"))
        assert any("DAWOS_API_KEY" in m for m in msgs)
        assert any("DAWOS_API_KEY" in r.message for r in caplog.records)
    finally:
        settings.api_key = original


def test_no_warning_on_custom_api_key(caplog):
    """A custom API key should not produce the default-key warning."""
    original = settings.api_key
    try:
        settings.api_key = "my-secure-production-key-abc123"
        with caplog.at_level(logging.WARNING):
            msgs = check_config(logger=logging.getLogger("test"))
        assert not any("DAWOS_API_KEY" in m for m in msgs)
    finally:
        settings.api_key = original


def test_returns_messages_without_logger():
    """check_config without a logger should still return message list."""
    original = settings.api_key
    try:
        settings.api_key = "changeme-generate-a-strong-key"
        msgs = check_config()
        assert isinstance(msgs, list)
        assert len(msgs) >= 1
        assert any("DAWOS_API_KEY" in m for m in msgs)
    finally:
        settings.api_key = original


def test_silent_defaults_not_warned(monkeypatch):
    """Settings in _SILENT_DEFAULTS should not produce messages."""
    # Ensure none of the silent defaults' env vars are set
    # (they shouldn't be in test environment anyway)
    msgs = check_config()
    # Silent defaults like host, port, log_level should not appear
    silent_vars = [
        "DAWOS_HOST",
        "DAWOS_PORT",
        "DAWOS_LOG_LEVEL",
        "DAWOS_LOG_FORMAT",
        "DAWOS_PING_TARGET",
        "DAWOS_RATE_LIMIT",
    ]
    for var in silent_vars:
        assert not any(var in m for m in msgs), f"{var} should be silent"


def test_check_config_returns_list():
    """Return type should always be a list of strings."""
    result = check_config()
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, str)


def test_info_logged_for_non_silent_setting(monkeypatch, caplog):
    """Settings not in _SILENT_DEFAULTS should produce info messages."""
    # Temporarily shrink _SILENT_DEFAULTS so 'retry_max' is detected
    original_silent = config_module._SILENT_DEFAULTS
    monkeypatch.setattr(
        config_module,
        "_SILENT_DEFAULTS",
        original_silent - {"retry_max"},
    )
    # Also ensure the env var is NOT set
    monkeypatch.delenv("DAWOS_RETRY_MAX", raising=False)

    with caplog.at_level(logging.INFO):
        msgs = check_config(logger=logging.getLogger("test"))

    assert any("DAWOS_RETRY_MAX" in m for m in msgs)
    info_records = [
        r
        for r in caplog.records
        if r.levelno == logging.INFO and "DAWOS_RETRY_MAX" in r.message
    ]
    assert len(info_records) >= 1
