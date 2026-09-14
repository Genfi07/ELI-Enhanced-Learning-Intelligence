"""ConversationSummarizer: resume conversaciones largas.

Diseño:
  - No depende de la BD. Recibe una lista de tuplas (rol, contenido) y
    devuelve un texto resumido. Esto lo hace trivialmente testeable.
  - La decisión "¿toca resumir?" también es pura: cuenta mensajes sin
    resumir contra el umbral.
  - El resumen NO es una Memory (que es sobre el usuario). Vive en
    Conversation.meta["summary_text"] porque es específico de esta
    conversación concreta.
  - Idempotente: si ya se resumió hasta el mensaje N, el siguiente resumen
    empieza en N+1.
  - Si el LLM falla, devuelve cadena vacía y no se actualiza el estado.
"""
from __future__ import annotations

from app.core.contracts.llm import LLMProvider
from app.core.schemas.llm import LLMMessage
from app.observability.logging import get_logger

log = get_logger(__name__)


SUMMARIZER_SYSTEM_PROMPT = """\
Resume la siguiente conversación entre un usuario y ELI (un asistente de IA).

Reglas:
  - Conserva SOLO información con valor futuro: hechos, preferencias,
    decisiones tomadas, contexto del problema en curso, y cualquier
    conclusión importante.
  - Descarta saludos, cortesías, y repeticiones.
  - Escribe en tercera persona ("el usuario pidió...", "ELI propuso...").
  - Máximo 200 palabras.
  - Formato: texto plano, sin markdown, sin listas.
  - Si no hay nada relevante que conservar, devuelve "Sin información relevante".
"""


class ConversationSummarizer:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        keep_recent: int = 20,
        max_summary_tokens: int = 400,
    ) -> None:
        self.llm = llm
        self.keep_recent = keep_recent
        self.max_summary_tokens = max_summary_tokens

    # ------------------------------------------------------------------ #
    # Decisión (pura)
    # ------------------------------------------------------------------ #
    def should_summarize(
        self,
        total_messages: int,
        summarized_count: int,
        threshold: int,
    ) -> bool:
        """True si hay suficientes mensajes sin resumir para justificar otro resumen."""
        unsummarized = max(0, total_messages - summarized_count)
        return unsummarized >= threshold

    def slice_to_summarize(
        self,
        all_messages: list[tuple[str, str]],
        summarized_count: int,
    ) -> list[tuple[str, str]]:
        """Devuelve solo los mensajes que hay que resumir en esta pasada.

        Preserva los `keep_recent` más nuevos sin resumir. Nunca toca los
        ya resumidos (`[:summarized_count]`).
        """
        total = len(all_messages)
        cutoff = max(summarized_count, total - self.keep_recent)
        return all_messages[summarized_count:cutoff]

    # ------------------------------------------------------------------ #
    # Resumen
    # ------------------------------------------------------------------ #
    async def summarize(
        self,
        messages: list[tuple[str, str]],
        *,
        model: str | None = None,
    ) -> str:
        """Devuelve el texto resumido. Cadena vacía si no hay nada que hacer
        o si el LLM falla (no lanza excepciones)."""
        if not messages:
            return ""

        transcript = "\n".join(
            f"{role.upper()}: {content}" for role, content in messages
        )
        user_prompt = f"CONVERSACIÓN A RESUMIR:\n\n{transcript}"

        try:
            response = await self.llm.generate(
                [
                    LLMMessage(role="system", content=SUMMARIZER_SYSTEM_PROMPT),
                    LLMMessage(role="user", content=user_prompt),
                ],
                model=model,
                temperature=0.2,
                max_tokens=self.max_summary_tokens,
            )
        except Exception as exc:
            log.warning("summarizer_llm_failed", error=str(exc))
            return ""

        text = (response.text or "").strip()
        return text