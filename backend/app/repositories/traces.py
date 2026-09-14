from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas.turn import TurnTrace
from app.db.models.trace import RequestTrace


class TraceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, trace: TurnTrace) -> None:
        self.session.add(
            RequestTrace(
                request_id=trace.request_id,
                user_id=trace.user_id,
                conversation_id=trace.conversation_id,
                route=trace.route,
                plan=trace.plan,
                steps=trace.steps,
                total_latency_ms=trace.total_latency_ms,
                status=trace.status,
                error=trace.error,
            )
        )
        await self.session.flush()