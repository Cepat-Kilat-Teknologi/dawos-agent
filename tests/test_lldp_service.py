"""Tests for services/lldp.py — LLDP neighbor discovery."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from dawos_agent.services import lldp


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# lldp_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lldp_status_running():
    proc = _mock_proc("lldp configuration")
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_status()

    assert result["running"] is True


@pytest.mark.asyncio
async def test_lldp_status_not_running():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_status()

    assert result["running"] is False


# ---------------------------------------------------------------------------
# lldp_neighbors
# ---------------------------------------------------------------------------

LLDP_JSON = json.dumps(
    {
        "lldp": {
            "interface": [
                {
                    "eth0": {
                        "chassis": {
                            "switch1": {
                                "name": "core-switch",
                            },
                        },
                        "port": {
                            "id": {"value": "ge-0/0/1"},
                            "descr": "uplink",
                        },
                        "ttl": 120,
                    },
                },
            ],
        },
    }
)


@pytest.mark.asyncio
async def test_lldp_neighbors():
    proc = _mock_proc(LLDP_JSON)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_neighbors()

    assert result["count"] == 1
    assert result["neighbors"][0]["local_interface"] == "eth0"
    assert result["neighbors"][0]["chassis_name"] == "core-switch"
    assert result["neighbors"][0]["port_id"] == "ge-0/0/1"


@pytest.mark.asyncio
async def test_lldp_neighbors_error():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_neighbors()

    assert result["count"] == 0


@pytest.mark.asyncio
async def test_lldp_neighbors_invalid_json():
    proc = _mock_proc("not json")
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_neighbors()

    assert result["count"] == 0


@pytest.mark.asyncio
async def test_lldp_neighbors_dict_interface():
    """Cover the case where interface is a dict instead of list."""
    data = json.dumps(
        {
            "lldp": {
                "interface": {
                    "eth0": {
                        "chassis": {"sw": {"name": "sw1"}},
                        "port": {"id": {"value": "p1"}, "descr": ""},
                        "ttl": 60,
                    },
                },
            },
        }
    )
    proc = _mock_proc(data)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_neighbors()

    assert result["count"] == 1


# ---------------------------------------------------------------------------
# lldp_interface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lldp_interface_found():
    data = json.dumps(
        {
            "lldp": {
                "interface": [
                    {
                        "eth0": {
                            "chassis": {"sw": {"name": "sw1"}},
                            "port": {"id": {"value": "p1"}, "descr": "uplink"},
                        },
                    },
                ],
            },
        }
    )
    proc = _mock_proc(data)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_interface("eth0")

    assert result["found"] is True
    assert result["interface"] == "eth0"
    assert len(result["neighbors"]) == 1


@pytest.mark.asyncio
async def test_lldp_interface_not_found():
    proc = _mock_proc("error", returncode=1)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_interface("eth99")

    assert result["found"] is False


@pytest.mark.asyncio
async def test_lldp_interface_invalid_json():
    """Cover JSON parse failure for interface query."""
    proc = _mock_proc("not json")
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_interface("eth0")

    assert result["found"] is False


@pytest.mark.asyncio
async def test_lldp_interface_dict_format():
    """Cover dict-style interface response."""
    data = json.dumps(
        {
            "lldp": {
                "interface": {
                    "eth0": {
                        "chassis": {"sw": {"name": "sw1"}},
                        "port": {"id": {"value": "p1"}, "descr": ""},
                    },
                },
            },
        }
    )
    proc = _mock_proc(data)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_interface("eth0")

    assert result["found"] is True


# ---------------------------------------------------------------------------
# _run / _extract_port_id / _extract_chassis_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_sudo():
    proc = _mock_proc("ok")
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        await lldp._run("lldpcli show neighbors", sudo=True)
        cmd = " ".join(m.call_args[0])
        assert cmd.startswith("sudo ")


def test_extract_port_id_dict():
    assert lldp._extract_port_id({"id": {"value": "ge-0/0/1"}}) == "ge-0/0/1"


def test_extract_port_id_string():
    assert lldp._extract_port_id({"id": "ge-0/0/1"}) == "ge-0/0/1"


def test_extract_port_id_empty():
    assert lldp._extract_port_id({}) == "{}"


def test_extract_chassis_name_not_dict():
    """Cover _extract_chassis_name when chassis is not a dict."""
    assert lldp._extract_chassis_name("not-a-dict") == ""


def test_extract_chassis_name_no_nested_dict():
    """Cover _extract_chassis_name when no values are dicts."""
    assert lldp._extract_chassis_name({"key": "string-value"}) == ""


@pytest.mark.asyncio
async def test_lldp_neighbors_non_dict_iface():
    """Cover continue branch when interface list contains a non-dict."""
    data = json.dumps(
        {
            "lldp": {
                "interface": [
                    "not-a-dict",
                    {
                        "eth0": {
                            "chassis": {"sw": {"name": "sw1"}},
                            "port": {"id": {"value": "p1"}, "descr": ""},
                            "ttl": 60,
                        },
                    },
                ],
            },
        }
    )
    proc = _mock_proc(data)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_neighbors()

    assert result["count"] == 1


@pytest.mark.asyncio
async def test_lldp_interface_non_dict_iface():
    """Cover continue branch in lldp_interface for non-dict entries."""
    data = json.dumps(
        {
            "lldp": {
                "interface": [
                    "not-a-dict",
                    {
                        "eth0": {
                            "chassis": {"sw": {"name": "sw1"}},
                            "port": {"id": {"value": "p1"}, "descr": ""},
                        },
                    },
                ],
            },
        }
    )
    proc = _mock_proc(data)
    with patch(
        "dawos_agent.services.lldp.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await lldp.lldp_interface("eth0")

    assert result["found"] is True
