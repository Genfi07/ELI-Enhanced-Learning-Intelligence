import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, db_session
from app.core.intent_classifier import HybridIntentClassifier
from app.core.orchestrator import Orchestrator
from app.core.plan_executor import PlanExecutor
from app.core.planner import Planner
from app.core.schemas.turn import TurnRequest
from app.llm.embeddings_router import build_embeddings_provider
from app.llm.router import ModelRouter, build_provider
from app.memory.service import MemoryService
from app.rag.service import KnowledgeService
from app.repositories.conversations import ConversationRepository
from app.tools.runtime import build_runtime

router = APIRouter(tags=["chat"])

_llm_provider = build_provider()
_embeddings = build_embeddings_provider()
_tool_runtime = build_runtime()

_orchestrator = Orchestrator(
    model_router=ModelRouter(provider=_llm_provider),
    memory=MemoryService(embeddings=_embeddings, llm=_llm_provider),
    knowledge=KnowledgeService(embeddings=_embeddings),
    classifier=HybridIntentClassifier(embeddings=_embeddings),
    planner=Planner(_llm_provider),
    executor=PlanExecutor(_llm_provider, tool_runtime=_tool_runtime),
)


class ChatIn(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(
    body: ChatIn,
    user_id: uuid.UUID = Depends(current_user_id),
    session: AsyncSession = Depends(db_session),
) -> StreamingResponse:
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    conv_id = body.conversation_id
    if conv_id is None:
        conv = await ConversationRepository(session).create(user_id, title=message[:60])
        await session.commit()
        conv_id = conv.id
    else:
        conv = await ConversationRepository(session).get_for_user(user_id, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

    req = TurnRequest(user_id=user_id, conversation_id=conv_id, message=message)

    async def event_source():
        try:
            async for event in _orchestrator.run_stream(req):
                yield _sse(event)
        except Exception as exc:
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )