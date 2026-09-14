from typing import Protocol
from app.core.schemas.turn import TurnTrace


class TraceRecorder(Protocol):
    async def record(self, trace: TurnTrace) -> None: ...