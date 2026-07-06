"""Tests for routers/ntp.py — NTP REST endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_ntp_status(client, headers):
    with patch(
        "dawos_agent.routers.ntp.ntp.ntp_status",
        return_value={
            "synced": True,
            "reference": "ntp.ubuntu.com",
            "stratum": 2,
            "system_time_offset": "",
            "last_offset": "",
            "frequency": "",
            "raw_output": "",
        },
    ):
        resp = await client.get("/api/v1/ntp/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["synced"] is True


@pytest.mark.asyncio
async def test_ntp_status_error(client, headers):
    with patch(
        "dawos_agent.routers.ntp.ntp.ntp_status",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/ntp/status", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_ntp_sources(client, headers):
    with patch(
        "dawos_agent.routers.ntp.ntp.ntp_sources",
        return_value={
            "count": 1,
            "sources": [
                {
                    "tally": "*",
                    "name": "ntp.ubuntu.com",
                    "stratum": 2,
                    "poll": 6,
                    "reach": "377",
                    "detail": "",
                }
            ],
            "raw_output": "",
        },
    ):
        resp = await client.get("/api/v1/ntp/sources", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


@pytest.mark.asyncio
async def test_ntp_sources_error(client, headers):
    with patch(
        "dawos_agent.routers.ntp.ntp.ntp_sources",
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/ntp/sources", headers=headers)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_ntp_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/ntp/status", headers=bad_headers)
    assert resp.status_code == 401
