"""Helper para registrar acciones en `audit_logs`.

Uso típico desde un endpoint admin:

    from app.admin.audit import record_audit

    await record_audit(
        session,
        actor_user_id=admin.id,
        action="user.block",
        entity_type="user",
        entity_id=str(target.id),
        before={"status": "ACTIVE"},
        after={"status": "BLOCKED"},
        meta={"reason": "abuse"},
        request=request,  # opcional: captura ip y user-agent
    )

Diseño:
  - No comitea. El caller decide cuándo hacer commit. Así la auditoría
    va en la misma transacción que el cambio que audita: o ambos se
    persisten, o ninguno.
  - `meta` se enriquece automáticamente con ip, user_agent y request_id
    si se pasa `request`.
  - Si el request_id está en contextvars (lo pone el middleware), se añade.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.system import AuditLog


def _client_meta(request: Request | None) -> dict[str, Any]:
    if request is None:
        return {}
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    rid = request.headers.get("x-request-id")
    out: dict[str, Any] = {}
    if ip:
        out["ip"] = ip
    if ua:
        out["user_agent"] = ua[:500]
    if rid:
        out["request_id"] = rid
    return out


async def record_audit(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    request: Request | None = None,
) -> AuditLog:
    """Registra una acción. NO comitea: el caller decide cuándo."""
    enriched: dict[str, Any] = dict(meta or {})
    enriched.update(_client_meta(request))

    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        meta=enriched,
    )
    session.add(entry)
    await session.flush()
    return entry