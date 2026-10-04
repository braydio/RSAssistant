"""Tests for centralized command authorization rules."""

from types import SimpleNamespace
from unittest.mock import patch

from utils.discord_permissions import _is_allowed


def test_operator_and_admin_role_permissions():
    role = SimpleNamespace(id=42)
    ctx = SimpleNamespace(author=SimpleNamespace(id=7, roles=[role]))
    with patch("utils.discord_permissions.DISCORD_OPERATOR_IDS", {8}), patch(
        "utils.discord_permissions.DISCORD_ADMIN_IDS", {9}
    ), patch("utils.discord_permissions.DISCORD_OPERATOR_ROLE_IDS", {42}), patch(
        "utils.discord_permissions.DISCORD_ADMIN_ROLE_IDS", {43}
    ):
        assert _is_allowed(ctx, admin=False)
        assert not _is_allowed(ctx, admin=True)


def test_admin_user_can_operate_but_unconfigured_users_are_denied():
    admin = SimpleNamespace(author=SimpleNamespace(id=9, roles=[]))
    unknown = SimpleNamespace(author=SimpleNamespace(id=99, roles=[]))
    with patch("utils.discord_permissions.DISCORD_OPERATOR_IDS", {8}), patch(
        "utils.discord_permissions.DISCORD_ADMIN_IDS", {9}
    ), patch("utils.discord_permissions.DISCORD_OPERATOR_ROLE_IDS", set()), patch(
        "utils.discord_permissions.DISCORD_ADMIN_ROLE_IDS", set()
    ):
        assert _is_allowed(admin, admin=True)
        assert _is_allowed(admin, admin=False)
        assert not _is_allowed(unknown, admin=False)
