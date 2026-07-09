"""Retry utilities for transient shell command failures.

Provides exponential-backoff retry logic for async operations that may
fail due to transient conditions (network timeouts, connection refused,
resource contention).  The :func:`with_retry` helper is designed to wrap
coroutine factories — callables that produce a fresh awaitable on each
invocation — so each retry starts a new attempt rather than re-awaiting
an already-consumed coroutine.

Transient detection
-------------------
The module defines a set of known transient error patterns
(``TRANSIENT_PATTERNS``) matched case-insensitively against error
messages.  Only errors matching these patterns are retried; all others
propagate immediately to avoid masking genuine failures.

Configuration
-------------
Retry behaviour is controlled by two settings in
:mod:`dawos_agent.config`:

* ``DAWOS_RETRY_MAX`` — maximum number of retry attempts (default 3).
  Set to ``0`` to disable retries entirely.
* ``DAWOS_RETRY_DELAY`` — base delay in seconds between attempts
  (default 1.0).  Each subsequent attempt waits ``base_delay * 2^n``
  seconds (exponential backoff).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

# Substrings in stderr/error messages that indicate transient failures.
# Matched case-insensitively against the full error text.
TRANSIENT_PATTERNS: tuple[str, ...] = (
    "connection refused",
    "connection reset",
    "timed out",
    "timeout",
    "resource temporarily unavailable",
    "no route to host",
    "network is unreachable",
    "broken pipe",
)


def is_transient(error_text: str) -> bool:
    """Return ``True`` if *error_text* matches a known transient pattern.

    The check is case-insensitive and matches any substring from
    :data:`TRANSIENT_PATTERNS`.

    Args:
        error_text: The error message or stderr output to examine.

    Returns:
        Whether the error appears to be a transient failure.
    """
    lower = error_text.lower()
    return any(pattern in lower for pattern in TRANSIENT_PATTERNS)


async def with_retry(
    coro_factory: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    **kwargs: Any,
) -> T:
    """Execute an async callable with exponential backoff on transient errors.

    Each retry attempt calls ``coro_factory(*args, **kwargs)`` to produce
    a fresh awaitable.  Only :class:`RuntimeError` and :class:`OSError`
    exceptions whose message matches a transient pattern are retried;
    all other exceptions propagate immediately.

    The delay between attempts follows exponential backoff:
    ``base_delay``, ``base_delay * 2``, ``base_delay * 4``, etc.

    Args:
        coro_factory: An async callable (not an already-awaited coroutine).
        *args: Positional arguments forwarded to *coro_factory*.
        max_retries: Maximum retry attempts after the initial try.
            Set to ``0`` to disable retries.
        base_delay: Seconds to wait before the first retry.  Subsequent
            retries double this value.
        **kwargs: Keyword arguments forwarded to *coro_factory*.

    Returns:
        The return value of *coro_factory* on a successful attempt.

    Raises:
        The last exception raised by *coro_factory* if all attempts
        are exhausted, or any non-transient exception immediately.
    """
    last_exc: BaseException | None = None

    for attempt in range(1 + max_retries):
        try:
            return await coro_factory(*args, **kwargs)
        except (RuntimeError, OSError) as exc:
            last_exc = exc
            if not is_transient(str(exc)):
                raise

            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                log.warning(
                    "Transient failure (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1,
                    1 + max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
            else:
                log.error(
                    "All %d attempts exhausted: %s",
                    1 + max_retries,
                    exc,
                )

    raise last_exc  # type: ignore[misc]
