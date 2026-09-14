"""Tests del helper de audit logging.

No probamos el middleware HTTP aquí; solo la función pura con una sesión
de BD real. Los tests verifican que se crean filas correctamente y que
los campos se serializan bien.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import record_audit
from app.db.models.system import AuditLog
from app.db.models.user import User
from tests.conftest import ROLE_USER_ID


@pytest.fixture
async def actor(session: AsyncSession) -> User:
    u = User(
        id=uuid.uuid4(),
        name="Admin User",
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        role_id=ROLE_USER_ID,
        status="ACTIVE",
    )
    session.add(u)
    await session.commit()
    return u


@pytest.mark.asyncio
async def test_record_basic_audit(session: AsyncSession, actor: User):
    entry = await record_audit(
        session,
        actor_user_id=actor.id,
        action="user.block",
        entity_type="user",
        entity_id=str(uuid.uuid4()),
        before={"status": "ACTIVE"},
        after={"status": "BLOCKED"},
        meta={"reason": "abuse"},
    )
    await session.commit()

    assert entry.id is not None
    assert entry.action == "user.block"
    assert entry.before == {"status": "ACTIVE"}
    assert entry.after == {"status": "BLOCKED"}
    assert entry.meta["reason"] == "abuse"


@pytest.mark.asyncio
async def test_record_audit_without_actor(session: AsyncSession):
    """El actor puede ser NULL (acciones del sistema)."""
    entry = await record_audit(
        session,
        actor_user_id=None,
        action="system.cleanup",
    )
    await session.commit()
    assert entry.actor_user_id is None


@pytest.mark.asyncio
async def test_audit_persists_and_is_queryable(
    session: AsyncSession, actor: User
):
    target_id = uuid.uuid4()
    await record_audit(
        session,
        actor_user_id=actor.id,
        action="config.update",
        entity_type="setting",
        entity_id="memory_top_k",
        before={"value": 5},
        after={"value": 10},
    )
    await session.commit()

    row = await session.scalar(
        select(AuditLog).where(
            AuditLog.action == "config.update",
            AuditLog.entity_id == "memory_top_k",
        )
    )
    assert row is not None
    assert row.before == {"value": 5}
    assert row.after == {"value": 10}


@pytest.mark.asyncio
async def test_audit_does_not_commit_implicitly(
    session: AsyncSession, actor: User
):
    """record_audit hace flush pero no commit. Sin commit explícito, no persiste.

    Verificamos mirando desde una segunda sesión que no ve el registro
    antes del commit explícito. Simplificamos: confirmamos que el entry
    existe en la sesión, pero el test principal ya cubre el commit.
    """
    entry = await record_audit(
        session,
        actor_user_id=actor.id,
        action="test.action",
    )
    # Antes del commit, la fila está en la sesión (flushed)
    assert entry.id is not None
    # Hacemos rollback y comprobamos que NO persiste
    await session.rollback()

    # Nueva query tras rollback: no debe encontrar la fila
    row = await session.scalar(
        select(AuditLog).where(AuditLog.id == entry.id)
    )
    assert row is None


@pytest.mark.asyncio
async def test_meta_is_serializable(session: AsyncSession, actor: User):
    """El campo meta acepta diccionarios anidados y tipos JSON básicos."""
    await record_audit(
        session,
        actor_user_id=actor.id,
        action="test.meta",
        meta={
            "nested": {"a": 1, "b": [1, 2, 3]},
            "bool": True,
            "null_value": None,
            "number": 3.14,
        },
    )
    await session.commit()
    row = await session.scalar(
        select(AuditLog).where(AuditLog.action == "test.meta")
    )
    assert row.meta["nested"]["b"] == [1, 2, 3]
    assert row.meta["bool"] is True