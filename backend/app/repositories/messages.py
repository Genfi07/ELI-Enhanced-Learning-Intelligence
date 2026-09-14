import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.message import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        model: str | None = None,
        request_id: str | None = None,
        meta: dict | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=model,
            request_id=request_id,
            meta=meta or {},
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def recent_for_conversation(
        self, conversation_id: uuid.UUID, limit: int
    ) -> list[Message]:
        """Últimos N mensajes en orden cronológico ascendente (más viejo primero)."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        rows = list((await self.session.scalars(stmt)).all())
        return list(reversed(rows))

    async def count_for_conversation(self, conversation_id: uuid.UUID) -> int:
        """Número total de mensajes en la conversación."""
        stmt = select(func.count()).select_from(Message).where(
            Message.conversation_id == conversation_id
        )
        return int(await self.session.scalar(stmt) or 0)