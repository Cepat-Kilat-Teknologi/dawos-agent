"""Regression tests for API rate-limit enforcement (DA-H02).

Verifies that ``SlowAPIMiddleware`` is mounted on the production app and
that, when a limit is configured, the limiter actually returns HTTP 429.
The shared test app disables the limit (see ``conftest``), so enforcement
is exercised here against a purpose-built app instance.
"""

from __future__ import annotations

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from starlette.testclient import TestClient

from dawos_agent.app import app as production_app


def test_app_mounts_slowapi_middleware() -> None:
    """The production app must include SlowAPIMiddleware in its stack.

    Without it the configured limiter is inert and ``DAWOS_RATE_LIMIT``
    has no effect (the original DA-H02 defect).
    """
    assert any(m.cls is SlowAPIMiddleware for m in production_app.user_middleware)


def test_rate_limit_returns_429_when_exceeded() -> None:
    """A configured per-IP limit yields HTTP 429 once exceeded."""
    app = FastAPI()
    limiter = Limiter(key_func=get_remote_address, default_limits=["2/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/ping")
    def ping() -> dict:
        """Return a trivial payload for limit testing."""
        return {"ok": True}

    client = TestClient(app)
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 429
