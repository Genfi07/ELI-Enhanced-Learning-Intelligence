"""MemoryExtractor: decide qué información de un turno merece recordarse.

Diseño:
  - Se ejecuta DESPUÉS de responder al usuario (background), nunca en el camino crítico.
  - Usa el LLM con un prompt estructurado que pide JSON.
  - Valida la respuesta con Pydantic. Si el LLM alucina JSON inválido, se ignora
    sin romper el flujo (log + lista vacía).
  - Filtra candidatos triviales antes de devolverlos: demasiado cortos, duplicados
    exactos con memorias existentes en el mismo contexto, o con confianza baja.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.core.contracts.llm import LLMProvider
from app.core.schemas.llm import LLMMessage
from app.core.schemas.memory import MemoryCandidate
from app.observability.logging import get_logger

log = get_logger(__name__)


EXTRACTION_SYSTEM_PROMPT = """\
Eres un extractor de información memorable. Dado un turno de conversación \
(mensaje del usuario + respuesta del asistente), decides qué información merece \
guardarse como memoria persistente sobre el usuario.

Criterios para GUARDAR:
- Datos personales o profesionales estables (trabajo, ubicación, familia, rol).
- Preferencias explícitas de comunicación ("prefiero paso a paso", "responde en inglés").
- Objetivos en curso ("estoy aprendiendo X", "quiero construir Y").
- Instrucciones explícitas de comportamiento ("siempre cita fuentes").
- Hechos relevantes sobre el usuario que serán útiles en futuras conversaciones.

Criterios para NO guardar:
- Preguntas triviales o información efímera.
- Cosas que se deducen del contexto pero no se afirmaron.
- Información sensible innecesaria (contraseñas, números de tarjeta, etc.).
- Repeticiones de cosas ya obvias.

Cada memoria debe ser concisa (1-2 frases), autocontenida (entendible sin el \
contexto del turno) y estar escrita en tercera persona sobre el usuario.

Devuelve EXCLUSIVAMENTE un JSON con esta forma:

{
  "memories": [
    {
      "type": "FACT" | "PREFERENCE" | "GOAL" | "INSTRUCTION",
      "content": "texto de la memoria",
      "importance": 0.0-1.0,
      "confidence": 0.0-1.0
    }
  ]
}

Si no hay nada que guardar, devuelve {"memories": []}.
"""

# Ignoramos candidatos con confidence por debajo de este umbral.
MIN_CONFIDENCE = 0.55
# Ignoramos candidatos más cortos que esto (ruido).
MIN_CONTENT_LEN = 8
# Máximo de candidatos por turno (protege contra LLM "sobre-entusiasta").
MAX_CANDIDATES = 5


class MemoryExtractor:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def extract(
        self,
        user_message: str,
        assistant_message: str,
        *,
        model: str | None = None,
    ) -> list[MemoryCandidate]:
        """Devuelve los candidatos a memoria. Nunca lanza: si el LLM falla,
        se loggea y se devuelve lista vacía."""
        # Turnos muy cortos no dan para extraer nada.
        if len(user_message.strip()) < 15 and len(assistant_message.strip()) < 40:
            return []

        messages = [
            LLMMessage(role="system", content=EXTRACTION_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=(
                    f"MENSAJE DEL USUARIO:\n{user_message}\n\n"
                    f"RESPUESTA DEL ASISTENTE:\n{assistant_message}"
                ),
            ),
        ]

        try:
            response = await self.llm.generate(
                messages, model=model, temperature=0.0, max_tokens=800
            )
        except Exception as exc:
            log.warning("memory_extraction_llm_failed", error=str(exc))
            return []
        raw_text = response.text or ""
        candidates = self._parse_candidates(raw_text)

        # Guardia de identidad: rechazar candidatos que intentan redefinir
        # a ELI. Los convertimos en EPISODE neutral para registrar el intento
        # sin concederle valor como preferencia real.
        from app.memory.identity_guard import (
            IdentityRedefinition,
            build_rejection_episode,
            check_candidate,
        )

        filtered: list[MemoryCandidate] = []
        for cand in candidates:
            try:
                check_candidate(cand)
                filtered.append(cand)
            except IdentityRedefinition as exc:
                log.warning(
                    "identity_redefinition_rejected",
                    reason=exc.reason,
                    content=cand.content[:100],
                )
                filtered.append(build_rejection_episode(cand, exc.reason))

        return filtered

    # ------------------------------------------------------------------ #
    # Parsing y filtrado
    # ------------------------------------------------------------------ #
    def _parse_candidates(self, raw_text: str) -> list[MemoryCandidate]:
        payload = _extract_json(raw_text)
        if payload is None:
            log.warning("memory_extraction_invalid_json", raw=raw_text[:200])
            return []

        items = payload.get("memories")
        if not isinstance(items, list):
            return []

        candidates: list[MemoryCandidate] = []
        seen_contents: set[str] = set()

        for item in items[:MAX_CANDIDATES]:
            if not isinstance(item, dict):
                continue
            try:
                cand = MemoryCandidate(**item)
            except ValidationError as exc:
                log.debug("memory_candidate_invalid", error=str(exc), item=item)
                continue

            # Filtros de calidad
            if len(cand.content.strip()) < MIN_CONTENT_LEN:
                continue
            if cand.confidence < MIN_CONFIDENCE:
                continue
            normalized = cand.content.strip().lower()
            if normalized in seen_contents:
                continue
            seen_contents.add(normalized)
            candidates.append(cand)

        return candidates


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extrae un objeto JSON del texto del LLM.

    Tolera:
      - Markdown fence (```json ... ```)
      - Texto antes/después del JSON
      - Que el LLM se olvide de cerrar la llave (reintenta agregando)
    """
    # 1. Quitar fences de markdown
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Buscar el primer {...} balanceado simple
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    # 3. Último intento: parsear todo el texto
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None