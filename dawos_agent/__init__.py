"""dawos-agent — PPP router management agent.

This package provides a FastAPI-based REST API that wraps the accel-ppp
Broadband Network Gateway (BNG) CLI and system utilities, exposing them
as authenticated HTTP endpoints.  It is designed to run as a long-lived
daemon on every accel-ppp node, allowing centralized management platforms
to inspect sessions, manage configuration, control services, and monitor
system health remotely.

Typical deployment::

    pip install dawos-agent
    dawos-agent              # or: python -m dawos_agent

Environment variables prefixed with ``DAWOS_`` (e.g. ``DAWOS_API_KEY``)
override the defaults defined in :mod:`dawos_agent.config`.
"""

from importlib.metadata import version

__version__ = version("dawos-agent")
