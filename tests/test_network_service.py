"""Tests for services/network.py — pure functions + mocked subprocess."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import network

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


IP_ADDR_JSON = json.dumps(
    [
        {
            "ifindex": 1,
            "ifname": "lo",
            "flags": ["LOOPBACK", "UP", "LOWER_UP"],
            "mtu": 65536,
            "operstate": "UNKNOWN",
            "address": "00:00:00:00:00:00",
            "link_type": "loopback",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "127.0.0.1",
                    "prefixlen": 8,
                    "scope": "host",
                }
            ],
        },
        {
            "ifindex": 2,
            "ifname": "eth0",
            "flags": ["BROADCAST", "MULTICAST", "UP", "LOWER_UP"],
            "mtu": 1500,
            "operstate": "UP",
            "address": "52:54:00:12:34:56",
            "link_type": "ether",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "10.0.0.1",
                    "prefixlen": 24,
                    "broadcast": "10.0.0.255",
                    "scope": "global",
                }
            ],
        },
        {
            "ifindex": 3,
            "ifname": "ppp0",
            "flags": ["POINTOPOINT", "MULTICAST", "NOARP", "UP", "LOWER_UP"],
            "mtu": 1492,
            "operstate": "UP",
            "address": "",
            "link_type": "ppp",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "100.64.0.1",
                    "prefixlen": 32,
                    "scope": "global",
                }
            ],
        },
    ]
)

IP_ROUTE_JSON = json.dumps(
    [
        {
            "dst": "default",
            "gateway": "10.0.0.254",
            "dev": "eth0",
            "protocol": "dhcp",
            "scope": "global",
            "metric": 100,
        },
        {
            "dst": "10.0.0.0/24",
            "dev": "eth0",
            "protocol": "kernel",
            "scope": "link",
            "prefsrc": "10.0.0.1",
        },
    ]
)

SINGLE_IFACE_JSON = json.dumps(
    [
        {
            "ifindex": 2,
            "ifname": "eth0",
            "flags": ["BROADCAST", "MULTICAST", "UP"],
            "mtu": 1500,
            "operstate": "UP",
            "address": "52:54:00:12:34:56",
            "link_type": "ether",
            "addr_info": [
                {
                    "family": "inet",
                    "local": "10.0.0.1",
                    "prefixlen": 24,
                    "broadcast": "10.0.0.255",
                    "scope": "global",
                }
            ],
        }
    ]
)


# ---------------------------------------------------------------------------
# _parse_ip_json
# ---------------------------------------------------------------------------


def test_parse_ip_json_empty():
    assert network._parse_ip_json("") == []


def test_parse_ip_json_invalid():
    assert network._parse_ip_json("not json at all") == []


def test_parse_ip_json_valid():
    result = network._parse_ip_json('[{"ifname": "eth0"}]')
    assert len(result) == 1
    assert result[0]["ifname"] == "eth0"


# ---------------------------------------------------------------------------
# list_interfaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_interfaces():
    proc = _mock_proc(IP_ADDR_JSON)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await network.list_interfaces()

    # lo should be excluded
    names = [i.name for i in result]
    assert "lo" not in names
    assert "eth0" in names
    assert "ppp0" in names
    assert len(result) == 2

    eth0 = [i for i in result if i.name == "eth0"][0]
    assert eth0.mac_address == "52:54:00:12:34:56"
    assert eth0.mtu == 1500
    assert eth0.state == "UP"
    assert eth0.addresses[0].address == "10.0.0.1"
    assert eth0.addresses[0].prefix_len == 24


@pytest.mark.asyncio
async def test_list_interfaces_include_loopback():
    proc = _mock_proc(IP_ADDR_JSON)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await network.list_interfaces(include_loopback=True)

    names = [i.name for i in result]
    assert "lo" in names
    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_interfaces_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Failed to list"):
        await network.list_interfaces()


# ---------------------------------------------------------------------------
# get_interface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_interface():
    proc = _mock_proc(SINGLE_IFACE_JSON)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        iface = await network.get_interface("eth0")

    assert iface.name == "eth0"
    assert iface.mac_address == "52:54:00:12:34:56"
    assert len(iface.addresses) == 1


@pytest.mark.asyncio
async def test_get_interface_not_found():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Interface not found"):
        await network.get_interface("eth99")


@pytest.mark.asyncio
async def test_get_interface_empty_json():
    proc = _mock_proc("[]")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="No data for"):
        await network.get_interface("eth99")


# ---------------------------------------------------------------------------
# configure_interface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_interface_add_address():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.configure_interface("eth0", address="10.0.0.5/24")

    assert "added 10.0.0.5/24" in msg


@pytest.mark.asyncio
async def test_configure_interface_remove_address():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.configure_interface("eth0", remove_address="10.0.0.5/24")

    assert "removed 10.0.0.5/24" in msg


@pytest.mark.asyncio
async def test_configure_interface_mtu():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.configure_interface("eth0", mtu=9000)

    assert "mtu=9000" in msg


@pytest.mark.asyncio
async def test_configure_interface_state():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.configure_interface("eth0", state="down")

    assert "state=down" in msg


@pytest.mark.asyncio
async def test_configure_interface_no_changes():
    msg = await network.configure_interface("eth0")
    assert msg == "No changes requested"


@pytest.mark.asyncio
async def test_configure_interface_multiple():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.configure_interface(
            "eth0",
            address="10.0.0.5/24",
            mtu=9000,
            state="up",
        )

    assert "added 10.0.0.5/24" in msg
    assert "mtu=9000" in msg
    assert "state=up" in msg


@pytest.mark.asyncio
async def test_configure_interface_invalid_state():
    """Invalid state values (not 'up'/'down') should be ignored."""
    msg = await network.configure_interface("eth0", state="invalid")
    assert msg == "No changes requested"


@pytest.mark.asyncio
async def test_configure_interface_error():
    proc = _mock_proc("RTNETLINK error", returncode=2)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Command failed"):
        await network.configure_interface("eth0", address="10.0.0.5/24")


# ---------------------------------------------------------------------------
# VLAN management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_vlan():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        name = await network.create_vlan("eth0", 100)

    assert name == "eth0.100"


@pytest.mark.asyncio
async def test_create_vlan_with_address():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        name = await network.create_vlan("eth0", 200, address="192.168.200.1/24")

    assert name == "eth0.200"


@pytest.mark.asyncio
async def test_create_vlan_error():
    proc = _mock_proc("exists", returncode=2)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError):
        await network.create_vlan("eth0", 100)


@pytest.mark.asyncio
async def test_delete_vlan():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.delete_vlan("eth0.100")

    assert "Deleted" in msg


# ---------------------------------------------------------------------------
# Route management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_routes():
    proc = _mock_proc(IP_ROUTE_JSON)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        routes = await network.list_routes()

    assert len(routes) == 2
    assert routes[0].destination == "default"
    assert routes[0].gateway == "10.0.0.254"
    assert routes[1].destination == "10.0.0.0/24"
    assert routes[1].source == "10.0.0.1"


@pytest.mark.asyncio
async def test_list_routes_error():
    proc = _mock_proc("", returncode=1)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Failed to list routes"):
        await network.list_routes()


@pytest.mark.asyncio
async def test_add_route():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.add_route("172.16.0.0/16", "10.0.0.254")

    assert "Route added" in msg


@pytest.mark.asyncio
async def test_add_route_with_device_and_metric():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.add_route(
            "172.16.0.0/16",
            "10.0.0.254",
            device="eth0",
            metric=200,
        )

    assert "Route added" in msg


@pytest.mark.asyncio
async def test_delete_route():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.delete_route("172.16.0.0/16")

    assert "Route deleted" in msg


@pytest.mark.asyncio
async def test_delete_route_with_gateway():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.delete_route("172.16.0.0/16", gateway="10.0.0.254")

    assert "Route deleted" in msg


# ---------------------------------------------------------------------------
# DNS management
# ---------------------------------------------------------------------------


def test_get_dns(tmp_path):
    resolv = tmp_path / "resolv.conf"
    resolv.write_text(
        "# Generated by NetworkManager\n"
        "search example.com corp.local\n"
        "nameserver 8.8.8.8\n"
        "nameserver 1.1.1.1\n"
    )
    config = network.get_dns(resolv_path=resolv)
    assert config.nameservers == ["8.8.8.8", "1.1.1.1"]
    assert config.search_domains == ["example.com", "corp.local"]


def test_get_dns_empty(tmp_path):
    resolv = tmp_path / "resolv.conf"
    resolv.write_text("")
    config = network.get_dns(resolv_path=resolv)
    assert config.nameservers == []


def test_get_dns_not_found(tmp_path):
    config = network.get_dns(resolv_path=tmp_path / "nonexistent")
    assert config.nameservers == []


def test_set_dns(tmp_path):
    resolv = tmp_path / "resolv.conf"
    network.set_dns(
        nameservers=["8.8.8.8", "8.8.4.4"],
        search_domains=["example.com"],
        resolv_path=resolv,
    )
    content = resolv.read_text()
    assert "nameserver 8.8.8.8" in content
    assert "nameserver 8.8.4.4" in content
    assert "search example.com" in content
    assert "dawos-agent" in content  # header comment


def test_set_dns_no_search(tmp_path):
    resolv = tmp_path / "resolv.conf"
    network.set_dns(nameservers=["1.1.1.1"], resolv_path=resolv)
    content = resolv.read_text()
    assert "nameserver 1.1.1.1" in content
    assert "search" not in content


# ---------------------------------------------------------------------------
# _run / _run_ok helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    """Verify sudo prefix is added when sudo=True."""
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ) as mock_sub:
        out, rc = await network._run("ip link show", sudo=True)
        cmd_arg = mock_sub.call_args[0][0]
        assert cmd_arg.startswith("sudo ")


@pytest.mark.asyncio
async def test_run_ok_raises():
    proc = _mock_proc("error msg", returncode=1)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Command failed"):
        await network._run_ok("ip link show")


# ---------------------------------------------------------------------------
# VLAN auto-detection (list_vlans)
# ---------------------------------------------------------------------------

VLAN_LINK_JSON = json.dumps(
    [
        {
            "ifindex": 10,
            "ifname": "eth0.100",
            "link": "eth0",
            "flags": ["BROADCAST", "MULTICAST", "UP", "LOWER_UP"],
            "mtu": 1500,
            "operstate": "UP",
            "address": "52:54:00:12:34:56",
            "linkinfo": {
                "info_kind": "vlan",
                "info_data": {
                    "protocol": "802.1Q",
                    "id": 100,
                    "flags": [],
                },
            },
            "addr_info": [
                {
                    "family": "inet",
                    "local": "192.168.100.1",
                    "prefixlen": 24,
                    "broadcast": "192.168.100.255",
                    "scope": "global",
                }
            ],
        },
        {
            "ifindex": 11,
            "ifname": "eth0.200",
            "link": "eth0",
            "flags": ["BROADCAST", "MULTICAST"],
            "mtu": 1500,
            "operstate": "DOWN",
            "address": "52:54:00:12:34:56",
            "linkinfo": {
                "info_kind": "vlan",
                "info_data": {
                    "protocol": "802.1Q",
                    "id": 200,
                    "flags": [],
                },
            },
            "addr_info": [],
        },
    ]
)


@pytest.mark.asyncio
async def test_list_vlans():
    proc = _mock_proc(VLAN_LINK_JSON)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        vlans = await network.list_vlans()

    assert len(vlans) == 2

    v1 = vlans[0]
    assert v1.name == "eth0.100"
    assert v1.parent == "eth0"
    assert v1.vlan_id == 100
    assert v1.protocol == "802.1Q"
    assert v1.state == "UP"
    assert v1.mac_address == "52:54:00:12:34:56"
    assert len(v1.addresses) == 1
    assert v1.addresses[0].address == "192.168.100.1"

    v2 = vlans[1]
    assert v2.name == "eth0.200"
    assert v2.vlan_id == 200
    assert v2.state == "DOWN"
    assert len(v2.addresses) == 0


@pytest.mark.asyncio
async def test_list_vlans_empty():
    proc = _mock_proc("[]")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        vlans = await network.list_vlans()

    assert vlans == []


@pytest.mark.asyncio
async def test_list_vlans_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Failed to list VLANs"):
        await network.list_vlans()


# ---------------------------------------------------------------------------
# VLAN state management (set_vlan_state)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_vlan_state_up():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.set_vlan_state("eth0.100", "up")

    assert "eth0.100" in msg
    assert "up" in msg


@pytest.mark.asyncio
async def test_set_vlan_state_down():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        msg = await network.set_vlan_state("eth0.100", "down")

    assert "down" in msg


@pytest.mark.asyncio
async def test_set_vlan_state_invalid():
    with pytest.raises(ValueError, match="Invalid state"):
        await network.set_vlan_state("eth0.100", "invalid")


@pytest.mark.asyncio
async def test_set_vlan_state_error():
    proc = _mock_proc("no such device", returncode=1)
    with patch(
        "dawos_agent.services.network.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="Command failed"):
        await network.set_vlan_state("eth0.999", "up")
