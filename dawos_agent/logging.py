"""Structured logging configuration for dawos-agent.

Provides two output formats controlled by the ``DAWOS_LOG_FORMAT``
environment variable:

* ``text`` (default) — human-readable coloured output, ideal for
  development and interactive debugging.
* ``json`` — machine-parseable JSON lines with ``timestamp``, ``level``,
  ``module``, ``message``, and ``request_id`` fields.  Suitable for
  production log aggregators (ELK, Loki, CloudWatch).

Call :func:`setup_logging` once at process startup (before Uvicorn
begins accepting requests) to install the chosen formatter on the
root logger.
"""

from __future__ import annotations

import logging
import sys

from .middleware import request_id_var


class _RequestIdFilter(logging.Filter):
    """Inject the current request ID into every log record.

    Reads the value from :data:`dawos_agent.middleware.request_id_var`.
    When no request context is active (e.g. during startup), the field
    defaults to an empty string so the JSON schema stays consistent.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = request_id_var.get("")  # type: ignore[attr-defined]
        return True


def setup_logging(*, level: str = "INFO", fmt: str = "text") -> None:
    """Configure the root logger with the specified format and level.

    Args:
        level: Python log level name (``DEBUG``, ``INFO``, ``WARNING``, …).
        fmt: Output format — ``"text"`` for human-readable or ``"json"``
            for structured JSON lines.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Remove existing handlers to avoid duplicates on re-init
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(_RequestIdFilter())

    if fmt == "json":
        from pythonjsonlogger.json import (  # pylint: disable=import-outside-toplevel
            JsonFormatter,
        )

        formatter = JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)
