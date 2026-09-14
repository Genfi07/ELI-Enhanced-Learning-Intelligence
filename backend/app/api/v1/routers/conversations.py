import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, db_session
from app.repositories.conversations import ConversationRepository
from app.repositories.messages import MessageRepository

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    model: str | None
    status: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tokens_in: int
    tokens_out: int
    model: str | None


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    user_id: uuid.UUID = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
) -> ConversationOut:
    conv = await ConversationRepository(session).create(user_id, title=body.title)
    await session.commit()
    return ConversationOut(id=conv.id, title=conv.title, model=conv.model, status=conv.status)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user_id: uuid.UUID = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
) -> list[ConversationOut]:
    rows = await ConversationRepository(session).list_for_user(user_id)
    return [ConversationOut(id=c.id, title=c.title, model=c.model, status=c.status) for c in rows]


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
) -> list[MessageOut]:
    conv = await ConversationRepository(session).get_for_user(user_id, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    msgs = await MessageRepository(session).recent_for_conversation(conversation_id, limit=200)
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            tokens_in=m.tokens_in,
            tokens_out=m.tokens_out,
            model=m.model,
        )
        for m in msgs
    ]


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
) -> None:
    ok = await ConversationRepository(session).delete_for_user(user_id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    await session.commit()