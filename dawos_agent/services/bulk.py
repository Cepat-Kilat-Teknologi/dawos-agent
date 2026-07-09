"""Bulk operation service — execute batch commands across multiple sessions.

Provides high-level functions that iterate over a list of targets,
execute the underlying single-item operation for each, and collect
per-item results.  Each item is handled independently so a failure
on one target does not cancel the remaining items.

Operations run sequentially to avoid overwhelming the accel-ppp CLI
port with concurrent connections.  For typical batch sizes (< 100)
the total wall-clock time is still under a few seconds.
"""

from __future__ import annotations

import logging

from . import accel, traffic

log = logging.getLogger(__name__)


async def bulk_terminate(usernames: list[str]) -> list[dict]:
    """Terminate sessions for a list of usernames.

    Each username is terminated independently.  Failures are captured
    per-item and do not abort the batch.

    Args:
        usernames: Subscriber usernames to disconnect.

    Returns:
        List of dicts with ``target``, ``success``, and ``message``
        keys, one per username in submission order.
    """
    results: list[dict] = []
    for username in usernames:
        try:
            output = await accel.terminate_session(username=username)
            results.append(
                {
                    "target": username,
                    "success": True,
                    "message": output.strip() or "Session terminated",
                }
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning("Bulk terminate failed for %s: %s", username, exc)
            results.append(
                {
                    "target": username,
                    "success": False,
                    "message": str(exc),
                }
            )
    return results


async def bulk_ratelimit(
    items: list[dict],
) -> list[dict]:
    """Change rate limits for multiple subscribers.

    Each item must contain ``username`` and ``rate`` keys.

    Args:
        items: List of dicts with ``username`` and ``rate`` entries.

    Returns:
        List of per-item result dicts.
    """
    results: list[dict] = []
    for item in items:
        username = item["username"]
        rate = item["rate"]
        try:
            message = await traffic.change_ratelimit(username, rate)
            results.append(
                {
                    "target": username,
                    "success": True,
                    "message": message,
                }
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning(
                "Bulk ratelimit failed for %s: %s",
                username,
                exc,
            )
            results.append(
                {
                    "target": username,
                    "success": False,
                    "message": str(exc),
                }
            )
    return results


async def bulk_shaper_restore(usernames: list[str]) -> list[dict]:
    """Restore RADIUS-assigned shapers for multiple subscribers.

    Args:
        usernames: Subscriber usernames to restore.

    Returns:
        List of per-item result dicts.
    """
    results: list[dict] = []
    for username in usernames:
        try:
            message = await traffic.restore_ratelimit(username)
            results.append(
                {
                    "target": username,
                    "success": True,
                    "message": message,
                }
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            log.warning(
                "Bulk shaper restore failed for %s: %s",
                username,
                exc,
            )
            results.append(
                {
                    "target": username,
                    "success": False,
                    "message": str(exc),
                }
            )
    return results
