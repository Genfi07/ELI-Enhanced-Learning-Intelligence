import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: uuid.UUID, title: str | None = None, model: str | None = None) -> Conversation:
        conv = Conversation(user_id=user_id, title=title or "Nueva conversación", model=model)
        self.session.add(conv)
        await self.session.flush()
        return conv

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_for_user(self, user_id: uuid.UUID, conv_id: uuid.UUID) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conv_id, Conversation.user_id == user_id
        )
        return await self.session.scalar(stmt)

    async def delete_for_user(self, user_id: uuid.UUID, conv_id: uuid.UUID) -> bool:
        conv = await self.get_for_user(user_id, conv_id)
        if conv is None:
            return False
        await self.session.delete(conv)
        return True