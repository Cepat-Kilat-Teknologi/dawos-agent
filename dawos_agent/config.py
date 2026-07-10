"""Application settings loaded from environment variables and ``.env`` files.

Uses `pydantic-settings <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>`_
to declare every tuneable knob with a sensible default.  All environment
variables are prefixed with ``DAWOS_`` (e.g. ``DAWOS_API_KEY``,
``DAWOS_PORT``).  A ``.env`` file in the working directory is loaded
automatically so operators can configure the agent without touching
systemd unit files.

The module exposes two convenience objects consumed throughout the
codebase:

* :data:`settings` — the resolved :class:`Settings` singleton.
* :data:`ACCEL_CONFIG` / :data:`BACKUP_DIR` — derived filesystem paths
  pointing to the accel-ppp configuration file and its backup sidecar
  directory.
"""

from __future__ import annotations

import logging
import os
import socket
from pathlib import Path

from pydantic_settings import BaseSettings

#: Insecure default API key shipped with the code.  The server refuses to
#: start while this value is in effect (see :func:`require_secure_api_key`).
_PLACEHOLDER_API_KEY = "changeme-generate-a-strong-key"


class Settings(BaseSettings):
    """Central configuration for the dawos-agent process.

    Every field maps to an environment variable with the ``DAWOS_`` prefix
    (e.g. ``node_name`` ↔ ``DAWOS_NODE_NAME``).  Fields are grouped by
    concern below.

    Attributes:
        node_name: Human-readable identifier for this BNG node.  Defaults
            to the system hostname and is included in health-check
            responses to help operators identify which node answered.
        host: IP address to bind the HTTP listener on.  ``0.0.0.0``
            listens on all interfaces.
        port: TCP port for the HTTP listener.  The default ``8470`` is
            chosen to avoid conflicts with accel-ppp's own CLI port (2001)
            and common web-server ports.
        api_key: Shared secret used for ``X-API-Key`` header
            authentication.  **Must** be replaced in production.
        accel_cmd: Absolute path to the ``accel-cmd`` CLI binary used to
            communicate with the running accel-ppp daemon.
        accel_cli_port: TCP port that the accel-ppp CLI telnet interface
            listens on (used by ``accel-cmd``).
        accel_config_path: Filesystem path to the main ``accel-ppp.conf``
            configuration file.
        accel_service_name: Systemd service unit name for accel-ppp,
            used when starting, stopping, or restarting the daemon.
        log_level: Uvicorn/Python log level string (e.g. ``debug``,
            ``info``, ``warning``, ``error``).
        log_format: Output format — ``"text"`` for human-readable or
            ``"json"`` for structured JSON lines.  Override via
            ``DAWOS_LOG_FORMAT``.
        ping_target: Host used by the internet reachability diagnostic
            check.  Override via ``DAWOS_PING_TARGET`` when the BNG
            node cannot reach Google DNS (e.g. air-gapped networks).
        rate_limit: Global per-IP rate limit string in ``slowapi``
            format (e.g. ``"120/minute"``, ``"5/second"``).  Override
            via ``DAWOS_RATE_LIMIT``.  Set to an empty string to
            disable rate limiting entirely.
        retry_max: Maximum number of retry attempts for transient shell
            command failures (e.g. accel-cmd connection refused).
            Set to ``0`` to disable retries.  Override via
            ``DAWOS_RETRY_MAX``.
        retry_delay: Base delay in seconds between retry attempts.
            Uses exponential backoff (1s, 2s, 4s, ...).  Override
            via ``DAWOS_RETRY_DELAY``.
        api_keys_file: Optional path to a JSON file mapping API keys
            to RBAC roles (``viewer``, ``operator``, ``admin``).
            When set, the agent supports multiple keys with different
            privilege levels.  The primary ``DAWOS_API_KEY`` always
            retains admin access regardless of the keys file content.
            Override via ``DAWOS_API_KEYS_FILE``.
        audit_buffer_size: Maximum number of audit log entries kept in
            the in-memory ring buffer.  Exposed via the ``GET
            /api/v1/audit`` admin endpoint.  Older entries are
            automatically evicted when the buffer is full.  Override
            via ``DAWOS_AUDIT_BUFFER_SIZE``.
        webhook_url: HTTP(S) URL to receive webhook notifications for
            mutating API operations.  When empty (default), webhooks
            are disabled.  Override via ``DAWOS_WEBHOOK_URL``.
        webhook_secret: Shared secret used to compute HMAC-SHA256
            signatures for webhook payloads.  The signature is sent
            in the ``X-Dawos-Signature`` header so receivers can
            verify authenticity.  When empty, the signature header
            is omitted.  Override via ``DAWOS_WEBHOOK_SECRET``.
    """

    # --- agent identity -------------------------------------------------------
    node_name: str = socket.gethostname()

    # --- network --------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8470

    # --- auth -----------------------------------------------------------------
    api_key: str = _PLACEHOLDER_API_KEY
    api_keys_file: str = ""

    # --- accel-ppp paths ------------------------------------------------------
    accel_cmd: str = "/usr/bin/accel-cmd"
    accel_cli_port: int = 2001
    accel_config_path: str = "/etc/accel-ppp.conf"
    accel_service_name: str = "accel-ppp"

    # --- logging --------------------------------------------------------------
    log_level: str = "info"
    log_format: str = "text"

    # --- diagnostics ----------------------------------------------------------
    ping_target: str = "8.8.8.8"

    # --- rate limiting --------------------------------------------------------
    rate_limit: str = "120/minute"

    # --- retry ----------------------------------------------------------------
    retry_max: int = 3
    retry_delay: float = 1.0

    # --- audit ----------------------------------------------------------------
    audit_buffer_size: int = 1000

    # --- webhooks -------------------------------------------------------------
    webhook_url: str = ""
    webhook_secret: str = ""

    model_config = {
        "env_prefix": "DAWOS_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton — imported everywhere as ``from dawos_agent.config import settings``.
settings = Settings()

# Derived paths
ACCEL_CONFIG = Path(settings.accel_config_path)
BACKUP_DIR = ACCEL_CONFIG.parent / "accel-ppp.d"

# ---------------------------------------------------------------------------
# Config completeness check
# ---------------------------------------------------------------------------

# Settings that are safe to leave at defaults and should NOT trigger warnings.
# These have sensible defaults that work out-of-the-box on standard installs.
_SILENT_DEFAULTS: frozenset[str] = frozenset(
    {
        "host",
        "port",
        "node_name",
        "accel_cmd",
        "accel_cli_port",
        "accel_config_path",
        "accel_service_name",
        "log_level",
        "log_format",
        "ping_target",
        "rate_limit",
        "retry_max",
        "retry_delay",
        "api_keys_file",
        "audit_buffer_size",
        "webhook_url",
        "webhook_secret",
    }
)


def check_config(logger: logging.Logger | None = None) -> list[str]:
    """Check configuration completeness and return a list of warnings.

    Inspects the active :data:`settings` singleton and reports:

    * **Security warning** if ``DAWOS_API_KEY`` is still the insecure
      default placeholder.
    * **Info messages** for optional settings that haven't been
      explicitly set via environment variables — helps operators
      discover new configuration knobs after an upgrade.

    Args:
        logger: If provided, warnings and info messages are emitted
            via this logger.  If ``None``, the function only returns
            the message list (useful for testing).

    Returns:
        A list of human-readable diagnostic strings.
    """
    messages: list[str] = []

    # Critical: API key must be changed in production
    if settings.api_key == _PLACEHOLDER_API_KEY:
        msg = (
            "DAWOS_API_KEY is using the default placeholder — "
            "generate a strong key for production: "
            'python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
        messages.append(msg)
        if logger:
            logger.warning(msg)

    # Informational: detect settings that could be customised
    env_prefix = Settings.model_config.get("env_prefix", "DAWOS_")
    for field_name in Settings.model_fields:  # pylint: disable=not-an-iterable
        if field_name in _SILENT_DEFAULTS or field_name == "api_key":
            continue
        env_var = f"{env_prefix}{field_name.upper()}"
        if env_var not in os.environ:
            msg = f"Optional setting {env_var} not set — using default"
            messages.append(msg)
            if logger:
                logger.info(msg)

    return messages


def require_secure_api_key() -> None:
    """Abort startup if the API key is still the insecure placeholder.

    Called from the process entry point
    (:func:`dawos_agent.__main__.main`) so the agent fails closed rather
    than serving the entire control plane under a publicly known key.

    Raises:
        RuntimeError: If ``DAWOS_API_KEY`` equals the shipped placeholder.
    """
    if settings.api_key == _PLACEHOLDER_API_KEY:
        raise RuntimeError(
            "Refusing to start: DAWOS_API_KEY is the insecure default "
            "placeholder. Generate a strong key, e.g. "
            'python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
