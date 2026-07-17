"""Tests for services/logs.py — log tail and SSE streaming."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dawos_agent.services import logs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_proc(stdout: str = "", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# _sse
# ---------------------------------------------------------------------------


def test_sse_format():
    result = logs._sse({"line": "hello"})
    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    parsed = json.loads(result[6:].strip())
    assert parsed == {"line": "hello"}


# ---------------------------------------------------------------------------
# get_logs
# ---------------------------------------------------------------------------

SAMPLE_LOGS = """\
Jul 06 10:00:00 bng accel-ppp: session started
Jul 06 10:00:01 bng accel-ppp: auth success
Jul 06 10:00:02 bng accel-ppp: session terminated
"""


@pytest.mark.asyncio
async def test_get_logs():
    proc = _mock_proc(SAMPLE_LOGS)
    with patch(
        "dawos_agent.services.logs.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await logs.get_logs(lines=50)

    assert result["count"] == 3
    assert result["source"] == "accel-ppp"
    assert "session started" in result["lines"][0]


@pytest.mark.asyncio
async def test_get_logs_custom_unit():
    proc = _mock_proc("line1\nline2")
    with patch(
        "dawos_agent.services.logs.asyncio.create_subprocess_exec",
        return_value=proc,
    ) as m:
        result = await logs.get_logs(lines=10, unit="frr")

    assert result["source"] == "frr"
    cmd = " ".join(m.call_args[0])
    assert "-u frr" in cmd
    assert "-n 10" in cmd


@pytest.mark.asyncio
async def test_get_logs_empty():
    proc = _mock_proc("")
    with patch(
        "dawos_agent.services.logs.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        result = await logs.get_logs()

    assert result["count"] == 0
    assert result["lines"] == []


@pytest.mark.asyncio
async def test_get_logs_error():
    proc = _mock_proc("error", returncode=1)
    with (
        patch(
            "dawos_agent.services.logs.asyncio.create_subprocess_exec",
            return_value=proc,
        ),
        pytest.raises(RuntimeError, match="Failed to read"),
    ):
        await logs.get_logs()


# ---------------------------------------------------------------------------
# log_stream_events (SSE generator)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_stream_events():
    """Mock journalctl -f output as an async iterator."""
    lines = [
        b"Jul 06 10:00:00 bng accel-ppp: event1\n",
        b"Jul 06 10:00:01 bng accel-ppp: event2\n",
    ]

    # Create mock async iterator for stdout
    async def mock_aiter():
        for line in lines:
            yield line

    proc = AsyncMock()
    proc.stdout = mock_aiter()
    proc.returncode = 0
    proc.terminate = MagicMock()
    proc.wait = AsyncMock()

    with patch(
        "dawos_agent.services.logs.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        events = []
        async for ev in logs.log_stream_events():
            events.append(ev)

    assert len(events) == 2
    data = json.loads(events[0][6:].strip())
    assert "event1" in data["line"]
    assert data["source"] == "accel-ppp"


@pytest.mark.asyncio
async def test_log_stream_events_empty_lines():
    """Empty lines should be skipped."""

    async def mock_aiter():
        yield b"actual line\n"
        yield b"\n"
        yield b"   \n"

    proc = AsyncMock()
    proc.stdout = mock_aiter()
    proc.returncode = 0
    proc.terminate = MagicMock()
    proc.wait = AsyncMock()

    with patch(
        "dawos_agent.services.logs.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        events = []
        async for ev in logs.log_stream_events():
            events.append(ev)

    assert len(events) == 1  # only the non-empty line


@pytest.mark.asyncio
async def test_log_stream_terminates_on_exit():
    """Ensure the process is terminated when the generator exits."""

    async def mock_aiter():
        yield b"line\n"

    proc = AsyncMock()
    proc.stdout = mock_aiter()
    proc.returncode = None  # still running
    proc.terminate = MagicMock()
    proc.wait = AsyncMock()

    with patch(
        "dawos_agent.services.logs.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        async for _ in logs.log_stream_events():
            pass

    proc.terminate.assert_called_once()


# ---------------------------------------------------------------------------
# _run helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_helper():
    proc = _mock_proc("output")
    with patch(
        "dawos_agent.services.logs.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        out, rc = await logs._run("journalctl -u test")

    assert out == "output"
    assert rc == 0


@pytest.mark.asyncio
async def test_run_helper_error():
    proc = _mock_proc("fail", returncode=1)
    with patch(
        "dawos_agent.services.logs.asyncio.create_subprocess_exec",
        return_value=proc,
    ):
        out, rc = await logs._run("bad command")

    assert rc == 1
