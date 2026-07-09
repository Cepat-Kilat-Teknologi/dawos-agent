"""Tests for the RBAC module — role definitions, key resolution, and keys file loading."""

from __future__ import annotations

import json

import pytest

from dawos_agent.rbac import KeyResolver, Role, load_keys_file, role_has_access

# ---------------------------------------------------------------------------
# Role hierarchy
# ---------------------------------------------------------------------------


class TestRoleHierarchy:
    """Verify the role privilege ordering."""

    def test_viewer_can_access_viewer(self) -> None:
        assert role_has_access(Role.VIEWER, Role.VIEWER)

    def test_viewer_cannot_access_operator(self) -> None:
        assert not role_has_access(Role.VIEWER, Role.OPERATOR)

    def test_viewer_cannot_access_admin(self) -> None:
        assert not role_has_access(Role.VIEWER, Role.ADMIN)

    def test_operator_can_access_viewer(self) -> None:
        assert role_has_access(Role.OPERATOR, Role.VIEWER)

    def test_operator_can_access_operator(self) -> None:
        assert role_has_access(Role.OPERATOR, Role.OPERATOR)

    def test_operator_cannot_access_admin(self) -> None:
        assert not role_has_access(Role.OPERATOR, Role.ADMIN)

    def test_admin_can_access_viewer(self) -> None:
        assert role_has_access(Role.ADMIN, Role.VIEWER)

    def test_admin_can_access_operator(self) -> None:
        assert role_has_access(Role.ADMIN, Role.OPERATOR)

    def test_admin_can_access_admin(self) -> None:
        assert role_has_access(Role.ADMIN, Role.ADMIN)


# ---------------------------------------------------------------------------
# Role enum values
# ---------------------------------------------------------------------------


class TestRoleEnum:
    """Verify Role enum string values."""

    def test_viewer_value(self) -> None:
        assert Role.VIEWER.value == "viewer"

    def test_operator_value(self) -> None:
        assert Role.OPERATOR.value == "operator"

    def test_admin_value(self) -> None:
        assert Role.ADMIN.value == "admin"

    def test_role_is_str_subclass(self) -> None:
        assert isinstance(Role.VIEWER, str)


# ---------------------------------------------------------------------------
# Keys file loading
# ---------------------------------------------------------------------------


class TestLoadKeysFile:
    """Verify JSON keys file parsing."""

    def test_load_valid_keys_file(self, tmp_path) -> None:
        keys_file = tmp_path / "keys.json"
        keys_file.write_text(
            json.dumps(
                {
                    "viewer-key": "viewer",
                    "operator-key": "operator",
                    "admin-key": "admin",
                }
            )
        )
        result = load_keys_file(str(keys_file))
        assert result == {
            "viewer-key": Role.VIEWER,
            "operator-key": Role.OPERATOR,
            "admin-key": Role.ADMIN,
        }

    def test_load_empty_object(self, tmp_path) -> None:
        keys_file = tmp_path / "keys.json"
        keys_file.write_text("{}")
        result = load_keys_file(str(keys_file))
        assert result == {}

    def test_load_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_keys_file("/nonexistent/keys.json")

    def test_load_invalid_json(self, tmp_path) -> None:
        keys_file = tmp_path / "keys.json"
        keys_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            load_keys_file(str(keys_file))

    def test_load_non_object_json(self, tmp_path) -> None:
        keys_file = tmp_path / "keys.json"
        keys_file.write_text('["a", "b"]')
        with pytest.raises(ValueError, match="JSON object"):
            load_keys_file(str(keys_file))

    def test_load_invalid_role_name(self, tmp_path) -> None:
        keys_file = tmp_path / "keys.json"
        keys_file.write_text(json.dumps({"key1": "superuser"}))
        with pytest.raises(ValueError, match="Invalid role"):
            load_keys_file(str(keys_file))


# ---------------------------------------------------------------------------
# KeyResolver
# ---------------------------------------------------------------------------


class TestKeyResolver:
    """Verify key-to-role resolution logic."""

    def test_primary_key_resolves_to_admin(self) -> None:
        resolver = KeyResolver(primary_key="master-key")
        assert resolver.resolve("master-key") == Role.ADMIN

    def test_unknown_key_returns_none(self) -> None:
        resolver = KeyResolver(primary_key="master-key")
        assert resolver.resolve("unknown-key") is None

    def test_empty_key_returns_none(self) -> None:
        resolver = KeyResolver(primary_key="master-key")
        assert resolver.resolve("") is None

    def test_rbac_disabled_without_keys_file(self) -> None:
        resolver = KeyResolver(primary_key="master-key")
        assert not resolver.rbac_enabled

    def test_rbac_enabled_with_keys_file(self, tmp_path) -> None:
        keys_file = tmp_path / "keys.json"
        keys_file.write_text(json.dumps({"viewer-key": "viewer"}))
        resolver = KeyResolver(primary_key="master-key", keys_file=str(keys_file))
        assert resolver.rbac_enabled

    def test_extra_key_resolves_to_configured_role(self, tmp_path) -> None:
        keys_file = tmp_path / "keys.json"
        keys_file.write_text(
            json.dumps(
                {
                    "mon-key": "viewer",
                    "ops-key": "operator",
                }
            )
        )
        resolver = KeyResolver(primary_key="master-key", keys_file=str(keys_file))
        assert resolver.resolve("mon-key") == Role.VIEWER
        assert resolver.resolve("ops-key") == Role.OPERATOR

    def test_primary_key_still_admin_with_keys_file(self, tmp_path) -> None:
        keys_file = tmp_path / "keys.json"
        keys_file.write_text(json.dumps({"other-key": "viewer"}))
        resolver = KeyResolver(primary_key="master-key", keys_file=str(keys_file))
        assert resolver.resolve("master-key") == Role.ADMIN

    def test_extra_key_takes_precedence_over_primary(self, tmp_path) -> None:
        """If the primary key appears in the keys file, the file wins."""
        keys_file = tmp_path / "keys.json"
        keys_file.write_text(json.dumps({"master-key": "viewer"}))
        resolver = KeyResolver(primary_key="master-key", keys_file=str(keys_file))
        # Keys file is checked first, so the file-defined role wins
        assert resolver.resolve("master-key") == Role.VIEWER

    def test_invalid_keys_file_logs_error_and_continues(self, tmp_path) -> None:
        """A bad keys file should not crash the resolver."""
        resolver = KeyResolver(
            primary_key="master-key",
            keys_file="/nonexistent/path.json",
        )
        # Should still work with primary key only
        assert resolver.resolve("master-key") == Role.ADMIN
        assert not resolver.rbac_enabled

    def test_keys_file_none_ignored(self) -> None:
        resolver = KeyResolver(primary_key="master-key", keys_file=None)
        assert not resolver.rbac_enabled
