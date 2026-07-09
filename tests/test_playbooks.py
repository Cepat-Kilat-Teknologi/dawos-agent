"""Tests for the operational playbooks API and service layer."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Playbook listing endpoint
# ---------------------------------------------------------------------------


class TestPlaybookList:
    """Verify GET /api/v1/playbooks endpoint."""

    @pytest.mark.asyncio
    async def test_list_playbooks(self, client, headers) -> None:
        resp = await client.get("/api/v1/playbooks", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 3
        names = {p["name"] for p in body["playbooks"]}
        assert names == {"health-check", "backup-config", "safe-restart"}

    @pytest.mark.asyncio
    async def test_list_playbooks_has_descriptions(self, client, headers) -> None:
        resp = await client.get("/api/v1/playbooks", headers=headers)
        body = resp.json()
        for playbook in body["playbooks"]:
            assert playbook["description"]
            assert playbook["role_required"] in ("viewer", "operator", "admin")

    @pytest.mark.asyncio
    async def test_viewer_can_list_playbooks(self, client, viewer_headers) -> None:
        resp = await client.get("/api/v1/playbooks", headers=viewer_headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, client) -> None:
        resp = await client.get("/api/v1/playbooks")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Playbook execution endpoint
# ---------------------------------------------------------------------------


class TestPlaybookRun:
    """Verify POST /api/v1/playbooks/{name}/run endpoint."""

    @pytest.mark.asyncio
    async def test_unknown_playbook_returns_404(self, client, headers) -> None:
        resp = await client.post(
            "/api/v1/playbooks/nonexistent/run",
            headers=headers,
        )
        assert resp.status_code == 404
        assert "Unknown playbook" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_viewer_cannot_run_playbook(self, client, viewer_headers) -> None:
        resp = await client.post(
            "/api/v1/playbooks/health-check/run",
            headers=viewer_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_cannot_run_playbook(
        self,
        client,
        operator_headers,
    ) -> None:
        resp = await client.post(
            "/api/v1/playbooks/safe-restart/run",
            headers=operator_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# health-check playbook execution
# ---------------------------------------------------------------------------


class TestHealthCheckPlaybook:
    """Verify the health-check playbook logic."""

    @pytest.mark.asyncio
    async def test_health_check_all_ok(self, client, headers) -> None:
        with (
            patch(
                "dawos_agent.services.playbooks.accel.show_version",
                new_callable=AsyncMock,
                return_value="accel-ppp 1.13.0",
            ),
            patch(
                "dawos_agent.services.playbooks.accel.show_stat",
                new_callable=AsyncMock,
                return_value={"sessions": {"active": 42}},
            ),
            patch(
                "dawos_agent.services.playbooks.config_manager.read_config",
                return_value=("# config content", None),
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/health-check/run",
                headers=headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["playbook"] == "health-check"
        assert body["success"] is True
        assert len(body["steps"]) == 3
        assert all(s["success"] for s in body["steps"])

    @pytest.mark.asyncio
    async def test_health_check_version_fail_aborts(self, client, headers) -> None:
        with patch(
            "dawos_agent.services.playbooks.accel.show_version",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ):
            resp = await client.post(
                "/api/v1/playbooks/health-check/run",
                headers=headers,
            )
        body = resp.json()
        assert body["success"] is False
        assert len(body["steps"]) == 1
        assert body["steps"][0]["success"] is False
        assert "connection refused" in body["steps"][0]["detail"]

    @pytest.mark.asyncio
    async def test_health_check_stat_fail_continues(self, client, headers) -> None:
        with (
            patch(
                "dawos_agent.services.playbooks.accel.show_version",
                new_callable=AsyncMock,
                return_value="accel-ppp 1.13.0",
            ),
            patch(
                "dawos_agent.services.playbooks.accel.show_stat",
                new_callable=AsyncMock,
                side_effect=RuntimeError("stat error"),
            ),
            patch(
                "dawos_agent.services.playbooks.config_manager.read_config",
                return_value=("# config", None),
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/health-check/run",
                headers=headers,
            )
        body = resp.json()
        assert body["success"] is False
        assert len(body["steps"]) == 3
        assert body["steps"][0]["success"] is True
        assert body["steps"][1]["success"] is False
        assert body["steps"][2]["success"] is True

    @pytest.mark.asyncio
    async def test_health_check_config_missing(self, client, headers) -> None:
        with (
            patch(
                "dawos_agent.services.playbooks.accel.show_version",
                new_callable=AsyncMock,
                return_value="accel-ppp 1.13.0",
            ),
            patch(
                "dawos_agent.services.playbooks.accel.show_stat",
                new_callable=AsyncMock,
                return_value={"sessions": {"active": 0}},
            ),
            patch(
                "dawos_agent.services.playbooks.config_manager.read_config",
                side_effect=FileNotFoundError("not found"),
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/health-check/run",
                headers=headers,
            )
        body = resp.json()
        assert body["success"] is False
        assert body["steps"][2]["success"] is False


# ---------------------------------------------------------------------------
# backup-config playbook execution
# ---------------------------------------------------------------------------


class TestBackupConfigPlaybook:
    """Verify the backup-config playbook logic."""

    @pytest.mark.asyncio
    async def test_backup_config_all_ok(self, client, headers) -> None:
        with (
            patch(
                "dawos_agent.services.playbooks.config_manager.create_checkpoint",
                return_value="/etc/accel-ppp.d/backup-20260709.bak",
            ),
            patch(
                "dawos_agent.services.playbooks.config_manager.list_backups",
                return_value=[{"name": "backup-20260709.bak", "size": 1024}],
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/backup-config/run",
                headers=headers,
            )
        body = resp.json()
        assert body["playbook"] == "backup-config"
        assert body["success"] is True
        assert len(body["steps"]) == 2

    @pytest.mark.asyncio
    async def test_backup_config_create_fails(self, client, headers) -> None:
        with patch(
            "dawos_agent.services.playbooks.config_manager.create_checkpoint",
            side_effect=PermissionError("permission denied"),
        ):
            resp = await client.post(
                "/api/v1/playbooks/backup-config/run",
                headers=headers,
            )
        body = resp.json()
        assert body["success"] is False
        assert len(body["steps"]) == 1
        assert "permission denied" in body["steps"][0]["detail"]

    @pytest.mark.asyncio
    async def test_backup_config_verify_fails(self, client, headers) -> None:
        with (
            patch(
                "dawos_agent.services.playbooks.config_manager.create_checkpoint",
                return_value="/etc/accel-ppp.d/backup.bak",
            ),
            patch(
                "dawos_agent.services.playbooks.config_manager.list_backups",
                side_effect=OSError("cannot list"),
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/backup-config/run",
                headers=headers,
            )
        body = resp.json()
        assert body["success"] is False
        assert len(body["steps"]) == 2
        assert body["steps"][0]["success"] is True
        assert body["steps"][1]["success"] is False


# ---------------------------------------------------------------------------
# safe-restart playbook execution
# ---------------------------------------------------------------------------


class TestSafeRestartPlaybook:
    """Verify the safe-restart playbook logic."""

    @pytest.mark.asyncio
    async def test_safe_restart_all_ok(self, client, headers) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        with (
            patch(
                "dawos_agent.services.playbooks.config_manager.create_checkpoint",
                return_value="/etc/accel-ppp.d/backup.bak",
            ),
            patch(
                "dawos_agent.services.playbooks.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
            patch(
                "dawos_agent.services.playbooks.accel.show_version",
                new_callable=AsyncMock,
                return_value="accel-ppp 1.13.0",
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/safe-restart/run",
                headers=headers,
            )
        body = resp.json()
        assert body["playbook"] == "safe-restart"
        assert body["success"] is True
        assert len(body["steps"]) == 3

    @pytest.mark.asyncio
    async def test_safe_restart_backup_fails_aborts(self, client, headers) -> None:
        with patch(
            "dawos_agent.services.playbooks.config_manager.create_checkpoint",
            side_effect=PermissionError("no access"),
        ):
            resp = await client.post(
                "/api/v1/playbooks/safe-restart/run",
                headers=headers,
            )
        body = resp.json()
        assert body["success"] is False
        assert len(body["steps"]) == 1
        assert body["steps"][0]["step"] == "pre-restart backup"

    @pytest.mark.asyncio
    async def test_safe_restart_systemctl_fails_aborts(self, client, headers) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"service not found"))
        with (
            patch(
                "dawos_agent.services.playbooks.config_manager.create_checkpoint",
                return_value="/etc/accel-ppp.d/backup.bak",
            ),
            patch(
                "dawos_agent.services.playbooks.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/safe-restart/run",
                headers=headers,
            )
        body = resp.json()
        assert body["success"] is False
        assert len(body["steps"]) == 2
        assert body["steps"][1]["success"] is False

    @pytest.mark.asyncio
    async def test_safe_restart_verify_fails(self, client, headers) -> None:
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        with (
            patch(
                "dawos_agent.services.playbooks.config_manager.create_checkpoint",
                return_value="/etc/accel-ppp.d/backup.bak",
            ),
            patch(
                "dawos_agent.services.playbooks.asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                return_value=mock_proc,
            ),
            patch(
                "dawos_agent.services.playbooks.accel.show_version",
                new_callable=AsyncMock,
                side_effect=RuntimeError("daemon unresponsive"),
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/safe-restart/run",
                headers=headers,
            )
        body = resp.json()
        assert body["success"] is False
        assert len(body["steps"]) == 3
        assert body["steps"][2]["success"] is False
        assert "unresponsive" in body["steps"][2]["detail"]


# ---------------------------------------------------------------------------
# Response structure validation
# ---------------------------------------------------------------------------


class TestPlaybookResponseStructure:
    """Verify response fields conform to schema."""

    @pytest.mark.asyncio
    async def test_step_has_required_fields(self, client, headers) -> None:
        with (
            patch(
                "dawos_agent.services.playbooks.accel.show_version",
                new_callable=AsyncMock,
                return_value="1.13.0",
            ),
            patch(
                "dawos_agent.services.playbooks.accel.show_stat",
                new_callable=AsyncMock,
                return_value={"sessions": {"active": 0}},
            ),
            patch(
                "dawos_agent.services.playbooks.config_manager.read_config",
                return_value=("config", None),
            ),
        ):
            resp = await client.post(
                "/api/v1/playbooks/health-check/run",
                headers=headers,
            )
        body = resp.json()
        for step in body["steps"]:
            assert "step" in step
            assert "success" in step
            assert "detail" in step
