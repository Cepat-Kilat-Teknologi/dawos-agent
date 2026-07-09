"""Fire-and-forget webhook notifications for mutating API operations.

When ``DAWOS_WEBHOOK_URL`` is configured, every mutating HTTP request
(POST, PUT, PATCH, DELETE) triggers an asynchronous HTTP POST to the
webhook endpoint.  The delivery is non-blocking — it never delays the
API response to the original caller.

Payload authentication
----------------------
If ``DAWOS_WEBHOOK_SECRET`` is set, each payload is signed with
HMAC-SHA256 and the hex digest is sent in the ``X-Dawos-Signature``
header.  Receivers should recompute the HMAC over the raw request
body and compare it to the header value using a constant-time
comparison function.

Usage from middleware::

    from dawos_agent.webhooks import fire_webhook

    fire_webhook({
        "event": "api.request",
        "method": "POST",
        "path": "/api/v1/service/restart",
        "role": "admin",
        "status": 200,
    })
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging

import httpx

from .config import settings

log = logging.getLogger(__name__)

#: Reusable async HTTP client for webhook delivery.  Created lazily on
#: first use and shared across all deliveries for connection pooling.
_client: httpx.AsyncClient | None = None  # pylint: disable=invalid-name


def _get_client() -> httpx.AsyncClient:
    """Return the shared async HTTP client, creating it on first call."""
    global _client  # noqa: PLW0603  # pylint: disable=global-statement
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


def _sign(payload: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 hex digest for a payload.

    Args:
        payload: Raw JSON bytes to sign.
        secret: Shared secret string.

    Returns:
        Hex-encoded HMAC-SHA256 digest.
    """
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def _deliver(url: str, payload: bytes, headers: dict[str, str]) -> None:
    """Send the webhook POST and log failures without raising.

    This coroutine is meant to be wrapped in :func:`asyncio.create_task`
    so delivery errors never propagate to the caller.

    Args:
        url: Webhook endpoint URL.
        payload: JSON-encoded request body.
        headers: HTTP headers including content-type and optional signature.
    """
    try:
        client = _get_client()
        resp = await client.post(url, content=payload, headers=headers)
        if resp.status_code >= 400:
            log.warning(
                "Webhook delivery failed: status=%d url=%s",
                resp.status_code,
                url,
            )
    except Exception:  # pylint: disable=broad-exception-caught
        log.warning("Webhook delivery error: url=%s", url, exc_info=True)


def fire_webhook(event: dict) -> None:
    """Schedule a non-blocking webhook delivery.

    If ``DAWOS_WEBHOOK_URL`` is not configured, this function is a
    no-op.  Otherwise it serialises *event* to JSON, optionally signs
    it with ``DAWOS_WEBHOOK_SECRET``, and fires an ``asyncio`` task
    to deliver the POST request in the background.

    Args:
        event: Dictionary payload to send as the JSON body.  Typically
            contains ``event``, ``method``, ``path``, ``role``,
            ``status``, ``timestamp``, and ``request_id`` keys.
    """
    url = settings.webhook_url
    if not url:
        return

    payload = json.dumps(event, default=str).encode()
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if settings.webhook_secret:
        headers["X-Dawos-Signature"] = _sign(payload, settings.webhook_secret)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_deliver(url, payload, headers))
    except RuntimeError:
        # No running event loop — should not happen in normal operation.
        log.debug("No event loop for webhook delivery")
