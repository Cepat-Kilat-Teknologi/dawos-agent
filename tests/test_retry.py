"""Tests for the retry utility module."""

from __future__ import annotations

import asyncio

import pytest

from dawos_agent.retry import TRANSIENT_PATTERNS, is_transient, with_retry


# ---------------------------------------------------------------------------
# is_transient
# ---------------------------------------------------------------------------


class TestIsTransient:
    """Tests for the transient error detection helper."""

    @pytest.mark.parametrize(
        "text",
        [
            "Connection refused",
            "connect: connection refused",
            "Operation timed out",
            "read timeout",
            "Resource temporarily unavailable",
            "No route to host",
            "Network is unreachable",
            "Broken pipe",
        ],
    )
    def test_matches_transient_patterns(self, text: str) -> None:
        """Known transient error messages should be detected."""
        assert is_transient(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "command not found",
            "permission denied",
            "No such file or directory",
            "invalid argument",
            "syntax error",
            "",
        ],
    )
    def test_rejects_non_transient(self, text: str) -> None:
        """Non-transient errors should not match."""
        assert is_transient(text) is False

    def test_case_insensitive(self) -> None:
        """Pattern matching should be case-insensitive."""
        assert is_transient("CONNECTION REFUSED") is True
        assert is_transient("Timed Out") is True

    def test_patterns_tuple_not_empty(self) -> None:
        """TRANSIENT_PATTERNS should contain at least one pattern."""
        assert len(TRANSIENT_PATTERNS) > 0


# ---------------------------------------------------------------------------
# with_retry
# ---------------------------------------------------------------------------


class TestWithRetry:
    """Tests for the async retry wrapper."""

    async def test_success_no_retry(self) -> None:
        """A successful call should return immediately without retrying."""
        call_count = 0

        async def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await with_retry(succeed, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    async def test_retries_on_transient_runtime_error(self) -> None:
        """Transient RuntimeError should trigger retries."""
        call_count = 0

        async def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("accel-cmd error: connection refused")
            return "recovered"

        result = await with_retry(
            fail_then_succeed, max_retries=3, base_delay=0.01
        )
        assert result == "recovered"
        assert call_count == 3

    async def test_retries_on_transient_os_error(self) -> None:
        """Transient OSError should trigger retries."""
        call_count = 0

        async def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("Network is unreachable")
            return "recovered"

        result = await with_retry(
            fail_then_succeed, max_retries=2, base_delay=0.01
        )
        assert result == "recovered"
        assert call_count == 2

    async def test_raises_non_transient_immediately(self) -> None:
        """Non-transient errors should propagate without retrying."""
        call_count = 0

        async def fail_permanent() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("command not found")

        with pytest.raises(RuntimeError, match="command not found"):
            await with_retry(
                fail_permanent, max_retries=3, base_delay=0.01
            )
        assert call_count == 1

    async def test_raises_after_max_retries_exhausted(self) -> None:
        """Should raise the last exception when all retries are exhausted."""
        call_count = 0

        async def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("accel-cmd error: connection refused")

        with pytest.raises(RuntimeError, match="connection refused"):
            await with_retry(
                always_fail, max_retries=2, base_delay=0.01
            )
        assert call_count == 3  # 1 initial + 2 retries

    async def test_zero_retries_disables(self) -> None:
        """Setting max_retries=0 should disable retrying."""
        call_count = 0

        async def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("accel-cmd error: timed out")

        with pytest.raises(RuntimeError, match="timed out"):
            await with_retry(
                always_fail, max_retries=0, base_delay=0.01
            )
        assert call_count == 1

    async def test_passes_args_and_kwargs(self) -> None:
        """Arguments and keyword arguments should be forwarded."""
        async def echo(a: str, b: int, key: str = "") -> str:
            return f"{a}-{b}-{key}"

        result = await with_retry(
            echo, "hello", 42, key="world", max_retries=0, base_delay=0.01
        )
        assert result == "hello-42-world"

    async def test_non_runtime_os_error_propagates(self) -> None:
        """Exceptions other than RuntimeError/OSError should propagate."""
        async def fail_value() -> str:
            raise ValueError("bad value")

        with pytest.raises(ValueError, match="bad value"):
            await with_retry(
                fail_value, max_retries=3, base_delay=0.01
            )
