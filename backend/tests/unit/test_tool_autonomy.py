"""Tests del sistema de autonomía y autorización.

No tocan BD: fabricamos User y Role en memoria porque `authorize_tool`
solo lee `user.preferences`, `user.role.name` y `role.permissions`.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.schemas.tool import ToolManifest
from app.tools.autonomy import (
    DEFAULT_AUTONOMY_LEVEL,
    authorize_tool,
    get_user_autonomy_level,
    set_user_autonomy_level,
)


# --------------------------------------------------------------------------- #
# Fakes en memoria
# --------------------------------------------------------------------------- #
class FakePermission:
    def __init__(self, code: str) -> None:
        self.code = code


class FakeRole:
    def __init__(self, name: str, permissions: list[str] | None = None) -> None:
        self.name = name
        self.permissions = [FakePermission(c) for c in (permissions or [])]


class FakeUser:
    def __init__(
        self,
        role_name: str = "USER",
        preferences: dict | None = None,
        permissions: list[str] | None = None,
    ) -> None:
        self.id = uuid.uuid4()
        self.role = FakeRole(role_name, permissions)
        self.preferences = preferences or {}


def _manifest(
    name: str = "calc",
    *,
    min_autonomy: int = 2,
    perms: list[str] | None = None,
    requires_confirmation: bool = False,
    enabled: bool = True,
) -> ToolManifest:
    return ToolManifest(
        name=name,
        description="test tool",
        parameters={},
        required_permissions=perms or [],
        min_autonomy_level=min_autonomy,
        requires_confirmation=requires_confirmation,
        enabled=enabled,
    )


# --------------------------------------------------------------------------- #
# Lectura del nivel de autonomía
# --------------------------------------------------------------------------- #
def test_default_autonomy_for_user():
    u = FakeUser(role_name="USER")
    assert get_user_autonomy_level(u) == DEFAULT_AUTONOMY_LEVEL


def test_default_autonomy_for_admin_is_4():
    u = FakeUser(role_name="ADMIN")
    assert get_user_autonomy_level(u) == 4


def test_default_autonomy_for_super_admin_is_4():
    u = FakeUser(role_name="SUPER_ADMIN")
    assert get_user_autonomy_level(u) == 4


def test_explicit_autonomy_overrides_default():
    u = FakeUser(role_name="USER", preferences={"autonomy_level": 4})
    assert get_user_autonomy_level(u) == 4


def test_invalid_autonomy_falls_back():
    u = FakeUser(role_name="USER", preferences={"autonomy_level": 99})
    assert get_user_autonomy_level(u) == DEFAULT_AUTONOMY_LEVEL


def test_set_autonomy_level():
    u = FakeUser()
    set_user_autonomy_level(u, 3)
    assert u.preferences["autonomy_level"] == 3
    assert get_user_autonomy_level(u) == 3


def test_set_autonomy_out_of_range_raises():
    u = FakeUser()
    with pytest.raises(ValueError):
        set_user_autonomy_level(u, 5)
    with pytest.raises(ValueError):
        set_user_autonomy_level(u, -1)


# --------------------------------------------------------------------------- #
# Autorización
# --------------------------------------------------------------------------- #
def test_allow_when_everything_ok():
    u = FakeUser(role_name="USER", preferences={"autonomy_level": 2})
    res = authorize_tool(u, _manifest("calc", min_autonomy=2))
    assert res.decision == "ALLOW"
    assert res.user_autonomy_level == 2


def test_deny_when_autonomy_too_low():
    u = FakeUser(role_name="USER", preferences={"autonomy_level": 1})
    res = authorize_tool(u, _manifest("calc", min_autonomy=2))
    assert res.decision == "DENY"
    assert "autonomía" in res.reason.lower()


def test_deny_when_tool_disabled_in_db():
    u = FakeUser(preferences={"autonomy_level": 4})
    res = authorize_tool(
        u, _manifest("calc"), tool_enabled_in_db=False
    )
    assert res.decision == "DENY"
    assert "administrador" in res.reason.lower()


def test_deny_when_manifest_disabled():
    u = FakeUser(preferences={"autonomy_level": 4})
    res = authorize_tool(u, _manifest("calc", enabled=False))
    assert res.decision == "DENY"


def test_deny_when_missing_permissions():
    u = FakeUser(role_name="USER", preferences={"autonomy_level": 4})
    res = authorize_tool(u, _manifest("calc", perms=["tools.web"]))
    assert res.decision == "DENY"
    assert "tools.web" in res.reason


def test_allow_when_permissions_present():
    u = FakeUser(
        role_name="ADMIN",
        preferences={"autonomy_level": 4},
        permissions=["tools.web"],
    )
    res = authorize_tool(u, _manifest("calc", perms=["tools.web"]))
    assert res.decision == "ALLOW"


def test_require_confirmation_when_flagged():
    u = FakeUser(preferences={"autonomy_level": 4})
    res = authorize_tool(
        u, _manifest("send_email", requires_confirmation=True)
    )
    assert res.decision == "REQUIRE_CONFIRMATION"


def test_confirmation_takes_precedence_after_other_checks():
    """Si nivel y permisos fallan, devuelve DENY aunque la tool pida confirmación."""
    u = FakeUser(role_name="USER", preferences={"autonomy_level": 0})
    res = authorize_tool(
        u, _manifest("sensitive", min_autonomy=4, requires_confirmation=True)
    )
    assert res.decision == "DENY"


def test_admin_gets_level_4_by_default():
    u = FakeUser(role_name="SUPER_ADMIN")
    res = authorize_tool(u, _manifest("web", min_autonomy=3))
    assert res.decision == "ALLOW"
    assert res.user_autonomy_level == 4