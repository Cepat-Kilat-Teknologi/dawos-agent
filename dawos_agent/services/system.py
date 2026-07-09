"""System information and metrics collector.

Uses ``psutil`` to gather host-level CPU, memory, disk, and network
interface data for the BNG system monitoring dashboard.
"""

from __future__ import annotations

import platform
import socket
from datetime import datetime

import psutil

from ..models.schemas import (
    CpuInfo,
    DiskInfo,
    MemoryInfo,
    MetricsResponse,
    NetworkInterface,
    SystemInfoResponse,
)

_BYTES_PER_MB: int = 1024 * 1024
"""One mebibyte in bytes — used for memory size conversions."""

_BYTES_PER_GB: int = 1024**3
"""One gibibyte in bytes — used for disk size conversions."""


def get_system_info() -> SystemInfoResponse:
    """Gather comprehensive system information.

    Collects hostname, OS details, CPU usage, memory, disk utilisation,
    network interfaces, and boot time.

    Returns:
        A :class:`SystemInfoResponse` with all system metrics.
    """
    uname = platform.uname()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = list(psutil.getloadavg())

    interfaces: list[NetworkInterface] = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for name, addr_list in addrs.items():
        if name == "lo":
            continue
        ips = [a.address for a in addr_list if a.family == socket.AF_INET]
        is_up = stats.get(name, type("", (), {"isup": False})).isup
        interfaces.append(NetworkInterface(name=name, addresses=ips, is_up=is_up))

    return SystemInfoResponse(
        hostname=socket.gethostname(),
        os=f"{uname.system} {uname.release}",
        kernel=uname.release,
        arch=uname.machine,
        cpu=CpuInfo(
            count=psutil.cpu_count() or 1,
            percent=psutil.cpu_percent(interval=0.1),
            load_avg=load,
        ),
        memory=MemoryInfo(
            total_mb=mem.total // _BYTES_PER_MB,
            used_mb=mem.used // _BYTES_PER_MB,
            available_mb=mem.available // _BYTES_PER_MB,
            percent=mem.percent,
        ),
        disk=DiskInfo(
            total_gb=round(disk.total / _BYTES_PER_GB, 1),
            used_gb=round(disk.used / _BYTES_PER_GB, 1),
            free_gb=round(disk.free / _BYTES_PER_GB, 1),
            percent=disk.percent,
        ),
        interfaces=interfaces,
        boot_time=datetime.fromtimestamp(psutil.boot_time()),
    )


def get_metrics() -> MetricsResponse:
    """Return a quick metrics snapshot (CPU, memory, disk).

    Lighter weight than :func:`get_system_info` — omits interfaces
    and boot time.

    Returns:
        A :class:`MetricsResponse` with CPU, memory, and disk data.
    """
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = list(psutil.getloadavg())

    return MetricsResponse(
        cpu=CpuInfo(
            count=psutil.cpu_count() or 1,
            percent=psutil.cpu_percent(interval=0.1),
            load_avg=load,
        ),
        memory=MemoryInfo(
            total_mb=mem.total // _BYTES_PER_MB,
            used_mb=mem.used // _BYTES_PER_MB,
            available_mb=mem.available // _BYTES_PER_MB,
            percent=mem.percent,
        ),
        disk=DiskInfo(
            total_gb=round(disk.total / _BYTES_PER_GB, 1),
            used_gb=round(disk.used / _BYTES_PER_GB, 1),
            free_gb=round(disk.free / _BYTES_PER_GB, 1),
            percent=disk.percent,
        ),
    )
