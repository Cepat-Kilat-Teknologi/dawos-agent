"""Tests for the configuration completeness check."""

from __future__ import annotations

import logging

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
        "DAWOS_HOST", "DAWOS_PORT", "DAWOS_LOG_LEVEL",
        "DAWOS_LOG_FORMAT", "DAWOS_PING_TARGET", "DAWOS_RATE_LIMIT",
    ]
    for var in silent_vars:
        assert not any(var in m for m in msgs), f"{var} should be silent"


def test_check_config_returns_list():
    """Return type should always be a list of strings."""
    result = check_config()
    assert isinstance(result, list)
    for item in result:
        assert isinstance(item, str)
