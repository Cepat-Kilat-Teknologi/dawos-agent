"""Entry point for running dawos-agent as a standalone process.

Supports two invocation styles:

* ``python -m dawos_agent`` — module execution via the Python interpreter.
* ``dawos-agent`` — console-script entry point installed by pip/setuptools.

Both routes call :func:`main`, which starts a Uvicorn ASGI server hosting
the FastAPI application defined in :mod:`dawos_agent.app`.  Server bind
address, port, and log level are read from :data:`dawos_agent.config.settings`.
"""

from __future__ import annotations

import uvicorn

from .config import settings


def main() -> None:
    """Launch the Uvicorn ASGI server with the dawos-agent FastAPI app.

    Reads ``host``, ``port``, and ``log_level`` from the global
    :class:`~dawos_agent.config.Settings` singleton and starts the server
    in the foreground with access-log output enabled.
    """
    uvicorn.run(
        "dawos_agent.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        access_log=True,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
