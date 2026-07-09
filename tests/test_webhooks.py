"""Tests for the webhook notification system."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from dawos_agent.webhooks import _sign, fire_webhook

# ---------------------------------------------------------------------------
# HMAC signature
# ---------------------------------------------------------------------------


class TestSignature:
    """Verify HMAC-SHA256 signature computation."""

    def test_sign_produces_hex_digest(self) -> None:
        payload = b'{"event":"test"}'
        secret = "my-secret"
        result = _sign(payload, secret)
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        assert result == expected

    def test_sign_different_secrets_differ(self) -> None:
        payload = b'{"event":"test"}'
        sig_a = _sign(payload, "secret-a")
        sig_b = _sign(payload, "secret-b")
        assert sig_a != sig_b

    def test_sign_different_payloads_differ(self) -> None:
        secret = "my-secret"
        sig_a = _sign(b'{"a":1}', secret)
        sig_b = _sign(b'{"b":2}', secret)
        assert sig_a != sig_b


# ---------------------------------------------------------------------------
# fire_webhook
# ---------------------------------------------------------------------------


class TestFireWebhook:
    """Verify the fire-and-forget webhook dispatch."""

    def test_noop_when_url_not_configured(self) -> None:
        """No error or HTTP call when DAWOS_WEBHOOK_URL is empty."""
        with patch("dawos_agent.webhooks.settings") as mock_settings:
            mock_settings.webhook_url = ""
            mock_settings.webhook_secret = ""
            # Should return immediately without error
            fire_webhook({"event": "test"})

    @pytest.mark.asyncio
    async def test_delivers_to_configured_url(self) -> None:
        """When URL is set, an asyncio task should be created."""
        mock_deliver = AsyncMock()
        with (
            patch("dawos_agent.webhooks.settings") as mock_settings,
            patch("dawos_agent.webhooks._deliver", mock_deliver),
        ):
            mock_settings.webhook_url = "https://hooks.example.com/test"
            mock_settings.webhook_secret = ""
            fire_webhook({"event": "api.request", "method": "POST"})
            # Allow the asyncio task to execute
            import asyncio

            await asyncio.sleep(0.05)
            mock_deliver.assert_called_once()
            args = mock_deliver.call_args
            url = args[0][0]
            assert url == "https://hooks.example.com/test"

    @pytest.mark.asyncio
    async def test_includes_signature_when_secret_set(self) -> None:
        """X-Dawos-Signature header should be present with a secret."""
        mock_deliver = AsyncMock()
        with (
            patch("dawos_agent.webhooks.settings") as mock_settings,
            patch("dawos_agent.webhooks._deliver", mock_deliver),
        ):
            mock_settings.webhook_url = "https://hooks.example.com/test"
            mock_settings.webhook_secret = "test-secret-key"
            fire_webhook({"event": "test"})
            import asyncio

            await asyncio.sleep(0.05)
            mock_deliver.assert_called_once()
            headers = mock_deliver.call_args[0][2]
            assert "X-Dawos-Signature" in headers
            # Verify the signature is valid
            payload = mock_deliver.call_args[0][1]
            expected_sig = _sign(payload, "test-secret-key")
            assert headers["X-Dawos-Signature"] == expected_sig

    @pytest.mark.asyncio
    async def test_no_signature_when_secret_empty(self) -> None:
        """X-Dawos-Signature header should be absent without a secret."""
        mock_deliver = AsyncMock()
        with (
            patch("dawos_agent.webhooks.settings") as mock_settings,
            patch("dawos_agent.webhooks._deliver", mock_deliver),
        ):
            mock_settings.webhook_url = "https://hooks.example.com/test"
            mock_settings.webhook_secret = ""
            fire_webhook({"event": "test"})
            import asyncio

            await asyncio.sleep(0.05)
            mock_deliver.assert_called_once()
            headers = mock_deliver.call_args[0][2]
            assert "X-Dawos-Signature" not in headers

    @pytest.mark.asyncio
    async def test_payload_is_json(self) -> None:
        """The delivered payload should be valid JSON."""
        mock_deliver = AsyncMock()
        with (
            patch("dawos_agent.webhooks.settings") as mock_settings,
            patch("dawos_agent.webhooks._deliver", mock_deliver),
        ):
            mock_settings.webhook_url = "https://hooks.example.com/test"
            mock_settings.webhook_secret = ""
            event = {"event": "api.request", "method": "POST", "path": "/test"}
            fire_webhook(event)
            import asyncio

            await asyncio.sleep(0.05)
            payload = mock_deliver.call_args[0][1]
            parsed = json.loads(payload)
            assert parsed["event"] == "api.request"
            assert parsed["method"] == "POST"
            assert parsed["path"] == "/test"


# ---------------------------------------------------------------------------
# _deliver error handling
# ---------------------------------------------------------------------------


class TestDeliver:
    """Verify _deliver handles errors gracefully."""

    @pytest.mark.asyncio
    async def test_deliver_logs_http_error(self, caplog) -> None:
        """HTTP errors should be logged, not raised."""
        from dawos_agent.webhooks import _deliver

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("dawos_agent.webhooks._get_client", return_value=mock_client):
            import logging

            with caplog.at_level(logging.WARNING, logger="dawos_agent.webhooks"):
                await _deliver(
                    "https://hooks.example.com/test",
                    b'{"test": true}',
                    {"Content-Type": "application/json"},
                )
        assert any("delivery failed" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_deliver_logs_connection_error(self, caplog) -> None:
        """Connection errors should be logged, not raised."""
        from dawos_agent.webhooks import _deliver

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("dawos_agent.webhooks._get_client", return_value=mock_client):
            import logging

            with caplog.at_level(logging.WARNING, logger="dawos_agent.webhooks"):
                await _deliver(
                    "https://hooks.example.com/test",
                    b'{"test": true}',
                    {"Content-Type": "application/json"},
                )
        assert any("delivery error" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_deliver_succeeds_on_2xx(self, caplog) -> None:
        """Successful delivery should not produce warnings."""
        from dawos_agent.webhooks import _deliver

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("dawos_agent.webhooks._get_client", return_value=mock_client):
            import logging

            with caplog.at_level(logging.WARNING, logger="dawos_agent.webhooks"):
                await _deliver(
                    "https://hooks.example.com/test",
                    b'{"test": true}',
                    {"Content-Type": "application/json"},
                )
        warning_records = [
            r
            for r in caplog.records
            if r.levelno >= logging.WARNING and "dawos_agent.webhooks" in r.name
        ]
        assert len(warning_records) == 0


# ---------------------------------------------------------------------------
# _get_client lazy creation
# ---------------------------------------------------------------------------


class TestGetClient:
    """Verify the lazy HTTP client creation."""

    def test_get_client_returns_httpx_client(self) -> None:
        import dawos_agent.webhooks as wh

        original = wh._client  # noqa: SLF001
        try:
            wh._client = None  # noqa: SLF001
            client = wh._get_client()
            assert isinstance(client, httpx.AsyncClient)
        finally:
            wh._client = original  # noqa: SLF001

    def test_get_client_returns_same_instance(self) -> None:
        import dawos_agent.webhooks as wh

        original = wh._client  # noqa: SLF001
        try:
            wh._client = None  # noqa: SLF001
            first = wh._get_client()
            second = wh._get_client()
            assert first is second
        finally:
            wh._client = original  # noqa: SLF001


# ---------------------------------------------------------------------------
# RuntimeError fallback (no event loop)
# ---------------------------------------------------------------------------


class TestNoEventLoop:
    """Verify fire_webhook handles missing event loop gracefully."""

    def test_no_event_loop_does_not_raise(self) -> None:
        """fire_webhook should not raise when no event loop is running."""
        with patch("dawos_agent.webhooks.settings") as mock_settings:
            mock_settings.webhook_url = "https://hooks.example.com/test"
            mock_settings.webhook_secret = ""
            with patch(
                "dawos_agent.webhooks.asyncio.get_running_loop",
                side_effect=RuntimeError("no running loop"),
            ):
                # Should not raise
                fire_webhook({"event": "test"})
