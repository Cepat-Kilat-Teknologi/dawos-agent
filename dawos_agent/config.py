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

import socket
from pathlib import Path

from pydantic_settings import BaseSettings


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
        ping_target: Host used by the internet reachability diagnostic
            check.  Override via ``DAWOS_PING_TARGET`` when the BNG
            node cannot reach Google DNS (e.g. air-gapped networks).
    """

    # --- agent identity -------------------------------------------------------
    node_name: str = socket.gethostname()

    # --- network --------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8470

    # --- auth -----------------------------------------------------------------
    api_key: str = "changeme-generate-a-strong-key"

    # --- accel-ppp paths ------------------------------------------------------
    accel_cmd: str = "/usr/bin/accel-cmd"
    accel_cli_port: int = 2001
    accel_config_path: str = "/etc/accel-ppp.conf"
    accel_service_name: str = "accel-ppp"

    # --- logging --------------------------------------------------------------
    log_level: str = "info"

    # --- diagnostics ----------------------------------------------------------
    ping_target: str = "8.8.8.8"

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
