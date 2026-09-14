"""ContextBuilder: ensambla la ventana de contexto bajo presupuesto de tokens.

Diseño:
  - El system prompt base es mínimo. La identidad real de ELI viene del
    IdentityService y se inyecta como primer bloque de `extra_system_blocks`.
  - Los bloques de memoria, RAG y resultado de plan van también como extras.
  - Los mensajes antiguos se descartan primero cuando el presupuesto aprieta.
"""
from __future__ import annotations

from app.config.settings import get_settings
from app.core.schemas.llm import LLMMessage
from app.db.models.message import Message
from app.llm.base import rough_token_count


# Fallback por si IdentityService no responde. Nunca debería usarse en
# condiciones normales, pero evita que un fallo de BD deje el prompt vacío.
DEFAULT_SYSTEM_PROMPT = (
    "Eres ELI, un asistente de inteligencia artificial honesto, directo y preciso. "
    "Si no sabes algo, lo dices. No inventas información."
)


class ContextBuilder:
    def __init__(self, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> None:
        self.system_prompt = system_prompt

    def build(
        self,
        history: list[Message],
        user_message: str,
        *,
        max_tokens: int | None = None,
        extra_system_blocks: list[str] | None = None,
    ) -> list[LLMMessage]:
        settings = get_settings()
        budget = max_tokens or settings.max_context_tokens

        # Orden del system prompt:
        #   1. Bloques extra (identidad, memoria, RAG, plan) — en el orden dado.
        #   2. Fallback mínimo.
        # ELI ve su identidad primero. Los LLM prestan más atención al
        # comienzo y final del contexto; la identidad debe ir arriba.
        system_blocks: list[str] = []
        if extra_system_blocks:
            system_blocks.extend(extra_system_blocks)
        if self.system_prompt:
            system_blocks.append(self.system_prompt)
        system_text = "\n\n".join(b for b in system_blocks if b).strip()

        # Reservas de presupuesto
        used = rough_token_count(system_text)
        used += settings.max_response_tokens
        used += rough_token_count(user_message)

        # Historial: del más reciente al más antiguo, hasta agotar presupuesto.
        selected: list[LLMMessage] = []
        for msg in reversed(history[-settings.history_recent_messages :]):
            cost = rough_token_count(msg.content) + 4
            if used + cost > budget:
                break
            used += cost
            selected.append(
                LLMMessage(role=msg.role, content=msg.content)  # type: ignore[arg-type]
            )

        selected.reverse()

        messages: list[LLMMessage] = []
        if system_text:
            messages.append(LLMMessage(role="system", content=system_text))
        messages.extend(selected)
        messages.append(LLMMessage(role="user", content=user_message))
        return messages