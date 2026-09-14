"""StateInterpreter: traduce señales numéricas a un estado interno.

Diseño híbrido:
  - El StateCalculator produce señales deterministas (números, flags).
  - El StateInterpreter le pasa esas señales al LLM con un prompt corto
    y le pide un JSON con mood, energy, focus, curiosity.
  - El LLM NO ve la conversación cruda, solo el resumen de señales.
  - Usamos `response_format={"type": "json_object"}` para forzar JSON válido.
  - Si el LLM falla o devuelve JSON inválido, hay un fallback determinista.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.contracts.llm import LLMProvider
from app.core.schemas.llm import LLMMessage
from app.eli.state_signals import ConversationSignals
from app.observability.logging import get_logger

log = get_logger(__name__)


VALID_MOODS = (
    "curiosa",
    "tranquila",
    "reflexiva",
    "seria",
    "juguetona",
    "cansada",
    "inquieta",
)


INTERPRETER_PROMPT = """\
Eres el intérprete de estado interno de ELI. Recibes un resumen numérico
de una conversación reciente y devuelves cómo estaría ELI en este momento.

Responde EXCLUSIVAMENTE con un objeto JSON. Sin markdown. Sin
explicaciones. Sin texto adicional antes o después. Solo el JSON.

No ves la conversación. Solo ves las señales. No inventes nada que no
esté en las señales. Si las señales son ambiguas, elige el estado más
neutro.

Ánimos válidos: curiosa, tranquila, reflexiva, seria, juguetona, cansada, inquieta.

Reglas orientativas:
- Conversación técnica densa → seria o reflexiva.
- Conversación con humor → juguetona.
- Conversación larga (>20 turnos) → cansada o tranquila.
- Conversación corta y nueva → curiosa.
- Usuario cansado → tranquila (para no agobiar).
- Variedad temática alta → curiosa.
- Variedad temática baja (tema repetitivo) → tranquila o cansada.
- Mucho tiempo sin hablar (>120 min) → tranquila (recargada).

Niveles (0.0 a 1.0):
- energy: sube con el descanso, baja con conversaciones largas.
- focus: sube en conversaciones profundas, baja con temas cambiantes.
- curiosity: sube con temas nuevos, baja con repetición.

Formato EXACTO de respuesta:

{
  "mood": "curiosa",
  "energy": 0.8,
  "focus": 0.9,
  "curiosity": 0.85,
  "reason": "explicación breve en una frase"
}
"""


@dataclass
class InterpretedState:
    mood: str
    energy: float
    focus: float
    curiosity: float
    reason: str


class StateInterpreter:
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    async def interpret(
        self,
        signals: ConversationSignals,
        current_state: dict[str, Any],
        *,
        model: str | None = None,
    ) -> InterpretedState:
        user_prompt = self._build_prompt(signals, current_state)

        try:
             response = await self.llm.generate(
                [
                    LLMMessage(role="system", content=INTERPRETER_PROMPT),
                    LLMMessage(role="user", content=user_prompt),
                ],
                model=model,
                temperature=0.0,
                max_tokens=300,
                # response_format no soportado por gpt-oss-120b en Groq.
                # El prompt ya es muy estricto pidiendo solo JSON.
            )
        except Exception as exc:
            log.warning("state_interpreter_llm_failed", error=str(exc))
            return self._fallback(signals, current_state, reason="llm_failed")

        parsed = self._parse(response.text or "")
        if parsed is None:
            log.info(
                "state_interpreter_invalid_json",
                raw=(response.text or "")[:200],
            )
            return self._fallback(signals, current_state, reason="invalid_json")

        return parsed

    def _build_prompt(
        self, signals: ConversationSignals, current_state: dict[str, Any]
    ) -> str:
        current = (
            f"Estado actual: mood={current_state.get('mood')}, "
            f"energy={current_state.get('energy')}, "
            f"focus={current_state.get('focus')}, "
            f"curiosity={current_state.get('curiosity')}."
        )
        return (
            f"SEÑALES:\n{signals.signal_summary}\n\n"
            f"{current}\n\n"
            "Devuelve el nuevo estado en JSON."
        )

    def _parse(self, raw: str) -> InterpretedState | None:
        payload = _extract_json(raw)
        if payload is None:
            return None
        try:
            mood = str(payload["mood"]).strip().lower()
            if mood not in VALID_MOODS:
                mood = "tranquila"
            energy = _clamp(float(payload.get("energy", 0.7)))
            focus = _clamp(float(payload.get("focus", 0.7)))
            curiosity = _clamp(float(payload.get("curiosity", 0.7)))
            reason = str(payload.get("reason", "")).strip()[:200]
            return InterpretedState(
                mood=mood,
                energy=energy,
                focus=focus,
                curiosity=curiosity,
                reason=reason or "sin motivo especificado",
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.info("state_interpreter_parse_failed", error=str(exc))
            return None

    def _fallback(
        self,
        signals: ConversationSignals,
        current_state: dict[str, Any],
        *,
        reason: str,
    ) -> InterpretedState:
        energy = 0.7
        focus = 0.7
        curiosity = 0.6
        mood = "tranquila"

        if signals.is_technical:
            mood = "seria"
            focus = 0.9
        if signals.has_humor:
            mood = "juguetona"
            energy = 0.85
        if signals.is_long_conversation:
            energy -= 0.2
            focus -= 0.1
        if signals.minutes_since_last_interaction >= 120:
            energy = 0.9
            mood = "tranquila"
        if signals.user_seems_tired:
            energy -= 0.1
            mood = "tranquila"
        if signals.topic_variety > 0.7:
            curiosity = 0.85
            mood = "curiosa"
        if signals.topic_variety < 0.3 and signals.turns_count > 5:
            curiosity = 0.4

        return InterpretedState(
            mood=mood,
            energy=_clamp(energy),
            focus=_clamp(focus),
            curiosity=_clamp(curiosity),
            reason=f"fallback determinista ({reason})",
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None