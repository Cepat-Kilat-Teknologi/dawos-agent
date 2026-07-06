"""Tests for routers/dns_forwarding.py — DNS forwarding REST endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_dns_fwd_status(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.status",
        return_value={"running": True, "backend": "dnsmasq", "upstream_count": 2},
    ):
        resp = await client.get("/api/v1/dns/forwarding/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["running"] is True


@pytest.mark.asyncio
async def test_dns_fwd_status_error(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.status",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/dns/forwarding/status", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_dns_fwd_config(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.get_config",
        return_value={"servers": ["8.8.8.8"], "listen_address": "", "cache_size": 1000},
    ):
        resp = await client.get("/api/v1/dns/forwarding/config", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["servers"] == ["8.8.8.8"]


@pytest.mark.asyncio
async def test_dns_fwd_config_error(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.get_config",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/dns/forwarding/config", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_set_dns_fwd(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.set_forwarders",
        return_value={"servers": ["8.8.8.8"], "cache_size": 2000},
    ):
        resp = await client.put(
            "/api/v1/dns/forwarding/config",
            json={"servers": ["8.8.8.8"], "cache_size": 2000},
            headers=headers,
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_set_dns_fwd_runtime_error(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.set_forwarders",
        side_effect=RuntimeError("Failed to reload"),
    ):
        resp = await client.put(
            "/api/v1/dns/forwarding/config",
            json={"servers": ["8.8.8.8"]},
            headers=headers,
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_set_dns_fwd_error(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.set_forwarders",
        side_effect=Exception("boom"),
    ):
        resp = await client.put(
            "/api/v1/dns/forwarding/config",
            json={"servers": ["8.8.8.8"]},
            headers=headers,
        )
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_flush_dns_cache(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.flush_cache",
        return_value={"flushed": True},
    ):
        resp = await client.post("/api/v1/dns/forwarding/flush", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["flushed"] is True


@pytest.mark.asyncio
async def test_flush_dns_cache_runtime_error(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.flush_cache",
        side_effect=RuntimeError("Failed to flush"),
    ):
        resp = await client.post("/api/v1/dns/forwarding/flush", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_flush_dns_cache_error(client, headers):
    with patch(
        "dawos_agent.routers.dns_forwarding.dns_forwarding.flush_cache",
        side_effect=Exception("boom"),
    ):
        resp = await client.post("/api/v1/dns/forwarding/flush", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_dns_forwarding_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/dns/forwarding/status", headers=bad_headers)
    assert resp.status_code == 401
