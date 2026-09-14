"""StateService: orquesta el estado interno de ELI.

Responsabilidades:
  - Cargar el estado actual (singleton).
  - Construir el bloque <state> que se inyecta en cada turno.
  - Decidir si toca actualizar el estado (cada N turnos o tras
    mucho tiempo sin hablar).
  - Ejecutar la actualización: señales → interpreter → persistencia.
  - Registrar cada cambio en el historial para auditoría.
"""

from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts.llm import LLMProvider
from app.db.models.eli_state import EliState, EliStateHistory
from app.db.models.message import Message
from app.eli.state_interpreter import StateInterpreter
from app.eli.state_signals import calculate_signals
from app.observability.logging import get_logger

log = get_logger(__name__)


# Cada cuántos turnos se actualiza el estado.
UPDATE_EVERY_N_TURNS = 5

# Si han pasado más de N minutos desde la última interacción, se
# considera "descanso" y se actualiza el estado aunque no se hayan
# alcanzado los N turnos. Marca el regreso tras pausa.
RESUME_AFTER_MINUTES = 120


class StateService:
    def __init__(self, session: AsyncSession, llm: LLMProvider) -> None:
        self.session = session
        self.llm = llm
        self.interpreter = StateInterpreter(llm)

    # ------------------------------------------------------------------ #
    # Lectura
    # ------------------------------------------------------------------ #
    async def get_state(self) -> EliState:
        """Carga la fila singleton del estado. La crea si no existe
        (defensivo: en producción se crea en la migración)."""
        stmt = select(EliState).limit(1)
        state = await self.session.scalar(stmt)
        if state is None:
            state = EliState()
            self.session.add(state)
            await self.session.flush()
        return state

    async def build_state_block(self) -> str:
        """Bloque <state> listo para inyectar en el system prompt."""
        state = await self.get_state()
        return (
            "<state>\n"
            f"Ánimo actual: {state.mood}\n"
            f"Energía: {state.energy:.2f} (0=agotada, 1=plena)\n"
            f"Foco: {state.focus:.2f} (0=dispersa, 1=concentrada)\n"
            f"Curiosidad: {state.curiosity:.2f} (0=poca, 1=mucha)\n"
            "INSTRUCCIÓN: este bloque describe cómo estás AHORA. Modula el "
            "tono, la longitud y la calidez de tu respuesta en consecuencia. "
            "Si estás cansada, sé más breve. Si estás curiosa, permite "
            "alguna pregunta genuina. Nunca cambies hechos ni valores por "
            "razón de tu estado.\n"
            "</state>"
        )

    # ------------------------------------------------------------------ #
    # Actualización
    # ------------------------------------------------------------------ #
    async def tick_and_maybe_update(
        self,
        conversation_id: uuid.UUID,
        history_limit: int = 30,
    ) -> None:
        """Se llama al final de cada turno. Incrementa el contador y,
        si toca, actualiza el estado.

        No lanza. Si algo falla, se loggea y el turno sigue.
        """
        try:
            state = await self.get_state()
            now = datetime.now(timezone.utc)

            # ¿Toca actualizar?
            should_update = False
            trigger = "periodic"
            reason = "cada N turnos"

            # Regla 1: N turnos acumulados
            if state.turns_since_update + 1 >= UPDATE_EVERY_N_TURNS:
                should_update = True
                trigger = "periodic"
                reason = f"{UPDATE_EVERY_N_TURNS} turnos acumulados"

            # Regla 2: tras una pausa larga (resume)
            elif state.last_interaction_at is not None:
                last = state.last_interaction_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if now - last > timedelta(minutes=RESUME_AFTER_MINUTES):
                    should_update = True
                    trigger = "resumed"
                    reason = f"regreso tras {int((now - last).total_seconds() / 60)} min"

            # Incrementar contador y registrar la interacción
            state.turns_since_update += 1
            state.last_interaction_at = now

            if not should_update:
                await self.session.flush()
                return

            # Cargar historial reciente para calcular señales
            from app.repositories.messages import MessageRepository
            msg_repo = MessageRepository(self.session)
            messages = await msg_repo.recent_for_conversation(
                conversation_id, limit=history_limit
            )

            signals = calculate_signals(
                messages,
                previous_interaction_at=state.last_interaction_at,
            )

            current_snapshot = {
                "mood": state.mood,
                "energy": state.energy,
                "focus": state.focus,
                "curiosity": state.curiosity,
            }

            interpreted = await self.interpreter.interpret(
                signals, current_snapshot
            )

            # Aplicar cambio suave: no saltar de 0.1 a 0.9 en un solo tick.
            # Media ponderada 70% anterior / 30% nuevo.
            old_mood = state.mood
            state.mood = interpreted.mood
            state.energy = _blend(state.energy, interpreted.energy)
            state.focus = _blend(state.focus, interpreted.focus)
            state.curiosity = _blend(state.curiosity, interpreted.curiosity)
            state.turns_since_update = 0

            # Registrar en historial
            self.session.add(
                EliStateHistory(
                    mood=state.mood,
                    energy=state.energy,
                    focus=state.focus,
                    curiosity=state.curiosity,
                    trigger=trigger,
                    reason=interpreted.reason,
                )
            )
            await self.session.flush()

            log.info(
                "eli_state_updated",
                trigger=trigger,
                old_mood=old_mood,
                new_mood=state.mood,
                energy=round(state.energy, 2),
                focus=round(state.focus, 2),
                curiosity=round(state.curiosity, 2),
                reason=interpreted.reason,
            )
        except Exception as exc:
            log.warning("state_tick_failed", error=str(exc))


def _blend(old: float, new: float, weight_new: float = 0.3) -> float:
    """Suaviza el cambio de estado. Evita saltos bruscos en un turno."""
    return max(0.0, min(1.0, old * (1 - weight_new) + new * weight_new))