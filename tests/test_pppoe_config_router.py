"""Tests for routers/pppoe_config_router.py — PPPoE runtime config endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.models.schemas import (
    PppoeRuntimeConfigResponse,
    PppoeRuntimeConfigUpdateRequest,
)

# ---------------------------------------------------------------------------
# GET /api/v1/pppoe/runtime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pppoe_runtime_success(client, headers):
    """GET /pppoe/runtime returns current PPPoE runtime config."""
    mock_cfg = {
        "service_name": "internet",
        "ac_name": "bng-jakarta-1",
        "verbose": 1,
    }
    with patch(
        "dawos_agent.routers.pppoe_config_router.pppoe_config"
        ".get_pppoe_runtime_config",
        return_value=mock_cfg,
    ):
        resp = await client.get("/api/v1/pppoe/runtime", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["service_name"] == "internet"
    assert data["ac_name"] == "bng-jakarta-1"
    assert data["verbose"] == 1


@pytest.mark.asyncio
async def test_get_pppoe_runtime_not_found(client, headers):
    """GET /pppoe/runtime returns 404 when config file is missing."""
    with patch(
        "dawos_agent.routers.pppoe_config_router.pppoe_config"
        ".get_pppoe_runtime_config",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.get("/api/v1/pppoe/runtime", headers=headers)

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_pppoe_runtime_error(client, headers):
    """GET /pppoe/runtime returns 500 on unexpected error."""
    with patch(
        "dawos_agent.routers.pppoe_config_router.pppoe_config"
        ".get_pppoe_runtime_config",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/pppoe/runtime", headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# PUT /api/v1/pppoe/runtime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_pppoe_runtime_success(client, headers):
    """PUT /pppoe/runtime updates config and returns new state."""
    with (
        patch(
            "dawos_agent.routers.pppoe_config_router.pppoe_config"
            ".set_pppoe_runtime_config",
            return_value="ok",
        ),
        patch(
            "dawos_agent.routers.pppoe_config_router.reload_config",
            new_callable=AsyncMock,
        ),
        patch(
            "dawos_agent.routers.pppoe_config_router.pppoe_config"
            ".get_pppoe_runtime_config",
            return_value={
                "service_name": "new-svc",
                "ac_name": "new-ac",
                "verbose": 1,
            },
        ),
    ):
        resp = await client.put(
            "/api/v1/pppoe/runtime",
            json={
                "service_name": "new-svc",
                "ac_name": "new-ac",
                "verbose": 1,
            },
            headers=headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["service_name"] == "new-svc"
    assert data["ac_name"] == "new-ac"
    assert data["verbose"] == 1


@pytest.mark.asyncio
async def test_set_pppoe_runtime_partial_update(client, headers):
    """PUT /pppoe/runtime with partial fields updates only those."""
    with (
        patch(
            "dawos_agent.routers.pppoe_config_router.pppoe_config"
            ".set_pppoe_runtime_config",
            return_value="ok",
        ),
        patch(
            "dawos_agent.routers.pppoe_config_router.reload_config",
            new_callable=AsyncMock,
        ),
        patch(
            "dawos_agent.routers.pppoe_config_router.pppoe_config"
            ".get_pppoe_runtime_config",
            return_value={
                "service_name": "internet",
                "ac_name": "bng1",
                "verbose": 1,
            },
        ),
    ):
        resp = await client.put(
            "/api/v1/pppoe/runtime",
            json={"verbose": 1},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["verbose"] == 1


@pytest.mark.asyncio
async def test_set_pppoe_runtime_reload_failure(client, headers):
    """PUT /pppoe/runtime succeeds even if reload fails (save-first)."""
    with (
        patch(
            "dawos_agent.routers.pppoe_config_router.pppoe_config"
            ".set_pppoe_runtime_config",
            return_value="ok",
        ),
        patch(
            "dawos_agent.routers.pppoe_config_router.reload_config",
            new_callable=AsyncMock,
            side_effect=Exception("reload fail"),
        ),
        patch(
            "dawos_agent.routers.pppoe_config_router.pppoe_config"
            ".get_pppoe_runtime_config",
            return_value={
                "service_name": "svc",
                "ac_name": "",
                "verbose": 0,
            },
        ),
    ):
        resp = await client.put(
            "/api/v1/pppoe/runtime",
            json={"service_name": "svc"},
            headers=headers,
        )

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_set_pppoe_runtime_bad_value(client, headers):
    """PUT /pppoe/runtime returns 400 on ValueError."""
    with patch(
        "dawos_agent.routers.pppoe_config_router.pppoe_config"
        ".set_pppoe_runtime_config",
        side_effect=ValueError("At least one field must be provided"),
    ):
        resp = await client.put(
            "/api/v1/pppoe/runtime",
            json={},
            headers=headers,
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_pppoe_runtime_not_found(client, headers):
    """PUT /pppoe/runtime returns 404 when config file is missing."""
    with patch(
        "dawos_agent.routers.pppoe_config_router.pppoe_config"
        ".set_pppoe_runtime_config",
        side_effect=FileNotFoundError("missing"),
    ):
        resp = await client.put(
            "/api/v1/pppoe/runtime",
            json={"verbose": 1},
            headers=headers,
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_set_pppoe_runtime_error(client, headers):
    """PUT /pppoe/runtime returns 500 on unexpected error."""
    with patch(
        "dawos_agent.routers.pppoe_config_router.pppoe_config"
        ".set_pppoe_runtime_config",
        side_effect=Exception("fail"),
    ):
        resp = await client.put(
            "/api/v1/pppoe/runtime",
            json={"verbose": 1},
            headers=headers,
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pppoe_runtime_get_requires_auth(client, bad_headers):
    """GET /pppoe/runtime requires valid API key."""
    resp = await client.get("/api/v1/pppoe/runtime", headers=bad_headers)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pppoe_runtime_put_requires_auth(client, bad_headers):
    """PUT /pppoe/runtime requires valid API key."""
    resp = await client.put(
        "/api/v1/pppoe/runtime",
        json={"verbose": 1},
        headers=bad_headers,
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Pydantic model smoke tests
# ---------------------------------------------------------------------------


def test_pppoe_runtime_config_response_defaults():
    """PppoeRuntimeConfigResponse has sensible defaults."""
    resp = PppoeRuntimeConfigResponse()
    assert resp.service_name == ""
    assert resp.ac_name == ""
    assert resp.verbose == 0


def test_pppoe_runtime_config_update_request_defaults():
    """PppoeRuntimeConfigUpdateRequest defaults to all None."""
    req = PppoeRuntimeConfigUpdateRequest()
    assert req.service_name is None
    assert req.ac_name is None
    assert req.verbose is None


def test_pppoe_runtime_config_update_request_with_values():
    """PppoeRuntimeConfigUpdateRequest accepts valid values."""
    req = PppoeRuntimeConfigUpdateRequest(
        service_name="internet",
        ac_name="bng-1",
        verbose=1,
    )
    assert req.service_name == "internet"
    assert req.ac_name == "bng-1"
    assert req.verbose == 1


def test_pppoe_runtime_config_update_request_verbose_validation():
    """PppoeRuntimeConfigUpdateRequest rejects verbose > 1."""
    with pytest.raises(Exception):
        PppoeRuntimeConfigUpdateRequest(verbose=2)
