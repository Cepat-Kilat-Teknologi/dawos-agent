"""Tests for routers/firewall.py — endpoint tests with mocked services."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.models.schemas import FirewallStatus, SysctlStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_STATUS = FirewallStatus(
    enabled=True,
    backend="nftables",
    rules_count=15,
    nat_enabled=True,
    sysctl=SysctlStatus(ip_forward=True, ip6_forward=False),
)

MOCK_STATUS_DISABLED = FirewallStatus(
    enabled=False,
    backend="nftables",
    rules_count=0,
    nat_enabled=False,
    sysctl=SysctlStatus(ip_forward=False, ip6_forward=False),
)

MOCK_SYSCTL = SysctlStatus(ip_forward=True, ip6_forward=False)


# ---------------------------------------------------------------------------
# Firewall status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_firewall_status(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.get_firewall_status",
        new_callable=AsyncMock,
        return_value=MOCK_STATUS,
    ):
        resp = await client.get("/api/v1/firewall/status", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["nat_enabled"] is True
    assert data["backend"] == "nftables"
    assert data["sysctl"]["ip_forward"] is True


@pytest.mark.asyncio
async def test_firewall_status_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.get_firewall_status",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/firewall/status", headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rules(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.list_ruleset",
        new_callable=AsyncMock,
        return_value=("table ip filter { ... }", 5),
    ):
        resp = await client.get("/api/v1/firewall/rules", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert "filter" in data["raw_output"]
    assert data["rules_count"] == 5


@pytest.mark.asyncio
async def test_list_rules_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.list_ruleset",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.get("/api/v1/firewall/rules", headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# NAT masquerade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_masquerade(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.setup_masquerade",
        new_callable=AsyncMock,
        return_value="NAT masquerade enabled on eth0",
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/masquerade",
            headers=headers,
            json={"wan_interface": "eth0"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["wan_interface"] == "eth0"


@pytest.mark.asyncio
async def test_enable_masquerade_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.setup_masquerade",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.post(
            "/api/v1/firewall/nat/masquerade",
            headers=headers,
            json={"wan_interface": "eth0"},
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_disable_masquerade(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.remove_masquerade",
        new_callable=AsyncMock,
        return_value="NAT masquerade removed",
    ):
        resp = await client.delete("/api/v1/firewall/nat/masquerade", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_disable_masquerade_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.remove_masquerade",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no table"),
    ):
        resp = await client.delete("/api/v1/firewall/nat/masquerade", headers=headers)

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Save rules
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_rules(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.save_ruleset",
        new_callable=AsyncMock,
        return_value="Ruleset saved to /etc/nftables.conf",
    ):
        resp = await client.post("/api/v1/firewall/save", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_save_rules_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.save_ruleset",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.post("/api/v1/firewall/save", headers=headers)

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# sysctl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sysctl(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.get_sysctl",
        new_callable=AsyncMock,
        return_value=MOCK_SYSCTL,
    ):
        resp = await client.get("/api/v1/firewall/sysctl", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"]["ip_forward"] is True
    assert data["status"]["ip6_forward"] is False


@pytest.mark.asyncio
async def test_get_sysctl_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.get_sysctl",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.get("/api/v1/firewall/sysctl", headers=headers)

    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_set_sysctl(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.set_sysctl",
        new_callable=AsyncMock,
        return_value=SysctlStatus(ip_forward=True, ip6_forward=True),
    ):
        resp = await client.put(
            "/api/v1/firewall/sysctl",
            headers=headers,
            json={"ip_forward": True, "ip6_forward": True},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "on" in data["message"]


@pytest.mark.asyncio
async def test_set_sysctl_disable(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.set_sysctl",
        new_callable=AsyncMock,
        return_value=SysctlStatus(ip_forward=False, ip6_forward=False),
    ):
        resp = await client.put(
            "/api/v1/firewall/sysctl",
            headers=headers,
            json={"ip_forward": False, "ip6_forward": False},
        )

    assert resp.status_code == 200
    assert "off" in resp.json()["message"]


@pytest.mark.asyncio
async def test_set_sysctl_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.set_sysctl",
        new_callable=AsyncMock,
        side_effect=RuntimeError("fail"),
    ):
        resp = await client.put(
            "/api/v1/firewall/sysctl",
            headers=headers,
            json={"ip_forward": True},
        )

    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_firewall_requires_auth(client, bad_headers):
    resp = await client.get("/api/v1/firewall/status", headers=bad_headers)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# nft dry-run validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_ruleset(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.validate_ruleset",
        new_callable=AsyncMock,
        return_value={"valid": True, "detail": "Ruleset syntax OK"},
    ):
        resp = await client.post(
            "/api/v1/firewall/validate",
            headers=headers,
            json={"ruleset": "table ip test { }"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert "OK" in data["detail"]


@pytest.mark.asyncio
async def test_validate_ruleset_invalid(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.validate_ruleset",
        new_callable=AsyncMock,
        return_value={"valid": False, "detail": "syntax error"},
    ):
        resp = await client.post(
            "/api/v1/firewall/validate",
            headers=headers,
            json={"ruleset": "bad { syntax"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False


@pytest.mark.asyncio
async def test_validate_ruleset_missing_body(client, headers):
    resp = await client.post(
        "/api/v1/firewall/validate",
        headers=headers,
        json={"ruleset": ""},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_validate_ruleset_error(client, headers):
    with patch(
        "dawos_agent.routers.firewall.firewall.validate_ruleset",
        new_callable=AsyncMock,
        side_effect=Exception("fail"),
    ):
        resp = await client.post(
            "/api/v1/firewall/validate",
            headers=headers,
            json={"ruleset": "table ip x {}"},
        )

    assert resp.status_code == 500
