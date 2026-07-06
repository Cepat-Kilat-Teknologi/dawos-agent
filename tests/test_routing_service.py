"""Tests for services/routing.py — FRR vtysh wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import routing

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# _is_ip / _safe_int
# ---------------------------------------------------------------------------


def test_is_ip_valid():
    assert routing._is_ip("10.0.0.1") is True
    assert routing._is_ip("192.168.1.255") is True


def test_is_ip_invalid():
    assert routing._is_ip("not-an-ip") is False
    assert routing._is_ip("10.0.0") is False
    assert routing._is_ip("10.0.0.256") is False
    assert routing._is_ip("") is False


def test_safe_int():
    assert routing._safe_int("42") == 42
    assert routing._safe_int("abc") == 0
    assert routing._safe_int(None) == 0


# ---------------------------------------------------------------------------
# _vtysh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vtysh_success():
    proc = _mock_proc("BGP table version is 1")
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing._vtysh("show bgp summary")

    assert "BGP table" in result


@pytest.mark.asyncio
async def test_vtysh_failure():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ), pytest.raises(RuntimeError, match="vtysh failed"):
        await routing._vtysh("bad command")


# ---------------------------------------------------------------------------
# BGP
# ---------------------------------------------------------------------------

BGP_SUMMARY = """\
BGP router identifier 10.0.0.1, local AS number 65000, vrf-id 0
Neighbor        V   AS   MsgRcvd  MsgSent  InQ OutQ  Up/Down State   PfxRcd
10.0.0.2        4  65001     100      200    0    0 01:00:00 Establ       5
10.0.0.3        4  65002      50      100    0    0 00:30:00 Active       0
"""


@pytest.mark.asyncio
async def test_bgp_summary():
    proc = _mock_proc(BGP_SUMMARY)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bgp_summary()

    assert result["configured"] is True
    assert result["router_id"] == "10.0.0.1"
    assert result["local_as"] == "65000"
    assert len(result["neighbors"]) == 2
    assert result["total_prefixes"] == 5


@pytest.mark.asyncio
async def test_bgp_summary_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bgp_summary()

    assert result["configured"] is False


@pytest.mark.asyncio
async def test_bgp_routes():
    proc = _mock_proc(
        "*> 10.0.0.0/24  10.0.0.2  0 65001 i\n*> 10.1.0.0/24  10.0.0.3  0 65002 i"
    )
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bgp_routes()

    assert result["count"] > 0
    assert "10.0.0.0" in result["raw_output"]


@pytest.mark.asyncio
async def test_bgp_routes_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bgp_routes()

    assert result["count"] == 0


# ---------------------------------------------------------------------------
# OSPF
# ---------------------------------------------------------------------------

OSPF_OUTPUT = """\
 OSPF Routing Process, Router ID: 10.0.0.1
 Supports only single TOS (TOS0) routes
"""


@pytest.mark.asyncio
async def test_ospf_status():
    proc = _mock_proc(OSPF_OUTPUT)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.ospf_status()

    assert result["configured"] is True
    assert result["router_id"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_ospf_status_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.ospf_status()

    assert result["configured"] is False


OSPF_NEIGHBORS = """\
Neighbor ID   Pri State          Address        Interface
10.0.0.2       1 Full/DR        10.0.0.2       eth0:10.0.0.1
"""


@pytest.mark.asyncio
async def test_ospf_neighbors():
    proc = _mock_proc(OSPF_NEIGHBORS)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.ospf_neighbors()

    assert result["configured"] is True
    assert len(result["neighbors"]) == 1
    assert result["neighbors"][0]["neighbor_id"] == "10.0.0.2"


@pytest.mark.asyncio
async def test_ospf_neighbors_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.ospf_neighbors()

    assert result["configured"] is False


@pytest.mark.asyncio
async def test_ospf_routes():
    ospf_out = (
        "N    10.0.0.0/24       [10] area: 0.0.0.0\n"
        "                           via 10.0.0.2, eth0"
    )
    proc = _mock_proc(ospf_out)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.ospf_routes()

    assert result["count"] > 0


@pytest.mark.asyncio
async def test_ospf_routes_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.ospf_routes()

    assert result["count"] == 0


# ---------------------------------------------------------------------------
# _run helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ) as m:
        await routing._run("vtysh -c 'test'", sudo=True)
        cmd = m.call_args[0][0]
        assert cmd.startswith("sudo ")


@pytest.mark.asyncio
async def test_run_no_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ) as m:
        await routing._run("echo hello", sudo=False)
        cmd = m.call_args[0][0]
        assert not cmd.startswith("sudo ")


# ---------------------------------------------------------------------------
# RIP
# ---------------------------------------------------------------------------

RIP_STATUS = """\
Routing Protocol is "rip"
  Sending updates every 30 seconds with +/-50%, next due in 10 seconds
  Default version control: send version 2, receive version 2

  Network
    10.0.0.0/24
    192.168.1.0/24

  Neighbor(s):
    10.0.0.2
    10.0.0.3
"""


@pytest.mark.asyncio
async def test_rip_status():
    proc = _mock_proc(RIP_STATUS)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.rip_status()

    assert result["configured"] is True
    assert result["version"] == "2"
    assert len(result["networks"]) == 2
    assert "10.0.0.0/24" in result["networks"]
    assert len(result["neighbors"]) == 2
    assert "10.0.0.2" in result["neighbors"]


@pytest.mark.asyncio
async def test_rip_status_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.rip_status()

    assert result["configured"] is False


RIP_ROUTES = """\
Codes: R - RIP, C - connected, S - Static, O - OSPF, B - BGP

     Network            Next Hop         Metric From            Tag Time
R(n) 10.0.0.0/24        via 10.0.0.2     2                      0 02:35
C    192.168.1.0/24     directly connected 1                      0
"""


@pytest.mark.asyncio
async def test_rip_routes():
    proc = _mock_proc(RIP_ROUTES)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.rip_routes()

    assert result["count"] == 2
    assert len(result["routes"]) == 2
    # First route: RIP learned
    r0 = result["routes"][0]
    assert r0["code"] == "R(n)"
    assert r0["network"] == "10.0.0.0/24"
    assert r0["nexthop"] == "10.0.0.2"
    assert r0["metric"] == 2
    # Second route: connected
    r1 = result["routes"][1]
    assert r1["code"] == "C"


@pytest.mark.asyncio
async def test_rip_routes_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.rip_routes()

    assert result["count"] == 0
    assert result["routes"] == []


@pytest.mark.asyncio
async def test_rip_routes_empty():
    proc = _mock_proc("Codes: R - RIP\n\n     Network            Next Hop\n")
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.rip_routes()

    assert result["count"] == 0
    assert result["routes"] == []


@pytest.mark.asyncio
async def test_rip_status_version_in_protocol_line():
    """Cover version extraction from the 'Routing Protocol' line itself."""
    rip_output = 'Routing Protocol is "rip" version 2\n'
    proc = _mock_proc(rip_output)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.rip_status()

    assert result["configured"] is True
    assert result["version"] == "2"


@pytest.mark.asyncio
async def test_rip_routes_skips_colon_codes():
    """Cover the code.endswith(':') guard that skips header-like lines."""
    rip_data = (
        "Redistrib: from RIP via kernel metric 1\n"
        "R(n) 10.0.0.0/24 via 10.0.0.2 2 eth0 00:10\n"
    )
    proc = _mock_proc(rip_data)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.rip_routes()

    # Only the R(n) line should be parsed, "Routes:" skipped
    assert result["count"] == 1
    assert result["routes"][0]["code"] == "R(n)"


# ---------------------------------------------------------------------------
# BFD
# ---------------------------------------------------------------------------

BFD_PEERS = """\
peer 10.0.0.2
  interface: eth0
  status: up
  uptime: 01:30:00

peer 10.0.0.3
  interface: eth1
  status: down
  uptime: 00:00:00
"""


@pytest.mark.asyncio
async def test_bfd_peers():
    proc = _mock_proc(BFD_PEERS)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bfd_peers()

    assert result["configured"] is True
    assert result["count"] == 2
    assert result["peers"][0]["peer"] == "10.0.0.2"
    assert result["peers"][0]["status"] == "up"
    assert result["peers"][1]["peer"] == "10.0.0.3"


@pytest.mark.asyncio
async def test_bfd_peers_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bfd_peers()

    assert result["configured"] is False
    assert result["peers"] == []


@pytest.mark.asyncio
async def test_bfd_summary():
    proc = _mock_proc("peer 10.0.0.2 control-pkt-in 100 control-pkt-out 100")
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bfd_summary()

    assert result["configured"] is True


@pytest.mark.asyncio
async def test_bfd_summary_not_configured():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bfd_summary()

    assert result["configured"] is False


@pytest.mark.asyncio
async def test_bfd_summary_empty():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.routing.asyncio.create_subprocess_shell",
        return_value=proc,
    ):
        result = await routing.bfd_summary()

    assert result["configured"] is False
