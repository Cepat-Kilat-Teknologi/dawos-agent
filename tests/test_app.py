"""Tests for app lifespan and system.py edge cases."""

import socket
from unittest.mock import MagicMock, patch

import pytest

from dawos_agent.services.system import get_system_info


def test_system_info_interface_down():
    """Interface with no isup attribute should default to False."""
    mock_addrs = {
        "eth99": [MagicMock(family=socket.AF_INET, address="192.168.1.1")],
    }
    # stats missing for eth99
    mock_stats = {}

    with (
        patch(
            "dawos_agent.services.system.psutil.net_if_addrs", return_value=mock_addrs
        ),
        patch(
            "dawos_agent.services.system.psutil.net_if_stats", return_value=mock_stats
        ),
    ):
        info = get_system_info()

    iface = [i for i in info.interfaces if i.name == "eth99"]
    assert len(iface) == 1
    assert iface[0].is_up is False


@pytest.mark.asyncio
async def test_app_lifespan():
    """Lifespan should log start and shutdown without error."""
    import logging

    from dawos_agent.app import app

    with patch.object(logging.getLogger("dawos_agent"), "info") as mock_log:
        async with app.router.lifespan_context(app):
            pass

    # Should have been called for start and shutdown
    assert mock_log.call_count == 2


def test_system_info_lo_excluded():
    """Loopback 'lo' must be filtered out (covers the `continue` branch)."""
    mock_addrs = {
        "lo": [MagicMock(family=socket.AF_INET, address="127.0.0.1")],
        "eth0": [MagicMock(family=socket.AF_INET, address="10.0.0.1")],
    }
    mock_stats = {
        "lo": MagicMock(isup=True),
        "eth0": MagicMock(isup=True),
    }

    with (
        patch(
            "dawos_agent.services.system.psutil.net_if_addrs", return_value=mock_addrs
        ),
        patch(
            "dawos_agent.services.system.psutil.net_if_stats", return_value=mock_stats
        ),
    ):
        info = get_system_info()

    names = [i.name for i in info.interfaces]
    assert "lo" not in names
    assert "eth0" in names
