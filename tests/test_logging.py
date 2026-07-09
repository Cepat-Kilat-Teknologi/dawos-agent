"""Tests for the structured logging configuration."""

from __future__ import annotations

import json
import logging

from dawos_agent.logging import setup_logging
from dawos_agent.middleware import request_id_var


def test_setup_text_format():
    """Text format should install a StreamHandler with request_id field."""
    setup_logging(level="DEBUG", fmt="text")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    handler = root.handlers[0]
    assert handler.formatter is not None
    assert "request_id" in handler.formatter._fmt


def test_setup_json_format(capsys):
    """JSON format should produce valid JSON log lines."""
    setup_logging(level="DEBUG", fmt="json")
    test_logger = logging.getLogger("test_json")
    test_logger.info("hello structured")

    captured = capsys.readouterr()
    line = captured.err.strip()
    data = json.loads(line)
    assert data["message"] == "hello structured"
    assert "timestamp" in data
    assert data["level"] == "INFO"


def test_request_id_injected_in_logs(capsys):
    """Log records should contain the current request_id from contextvars."""
    setup_logging(level="DEBUG", fmt="json")
    token = request_id_var.set("test-rid-123")
    try:
        logging.getLogger("test_rid").info("with rid")
        captured = capsys.readouterr()
        data = json.loads(captured.err.strip())
        assert data["request_id"] == "test-rid-123"
    finally:
        request_id_var.reset(token)


def test_request_id_empty_outside_request(capsys):
    """Outside a request context, request_id should be empty string."""
    setup_logging(level="DEBUG", fmt="json")
    token = request_id_var.set("")
    try:
        logging.getLogger("test_empty_rid").info("no context")
        captured = capsys.readouterr()
        data = json.loads(captured.err.strip())
        assert data["request_id"] == ""
    finally:
        request_id_var.reset(token)


def test_setup_replaces_existing_handlers():
    """Calling setup_logging twice should not duplicate handlers."""
    setup_logging(level="INFO", fmt="text")
    setup_logging(level="INFO", fmt="text")
    root = logging.getLogger()
    assert len(root.handlers) == 1
