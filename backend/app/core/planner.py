"""Planner: genera un ExecutionPlan para tareas complejas (ruta DEEP).

Diseño:
  - Pide al LLM un plan en JSON estricto.
  - Valida con Pydantic. Si el JSON es inválido, un único reintento.
  - Si el segundo intento también falla, devuelve un plan DEGRADADO de un
    solo paso `llm` con el mensaje original. Nunca rompe el turno.
  - El planner NO ejecuta pasos. Solo planifica.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.core.contracts.llm import LLMProvider
from app.core.schemas.llm import LLMMessage
from app.core.schemas.plan import ExecutionPlan, PlanStep
from app.observability.logging import get_logger

log = get_logger(__name__)


PLANNER_SYSTEM_PROMPT = """\
Eres el planificador de ELI. Recibes una tarea compleja del usuario y produces \
un plan de ejecución estructurado. NO respondes al usuario: solo planificas.

Reglas:
  - Máximo 6 pasos. Si la tarea requiere más, agrupa pasos coherentes.
  - Cada paso debe ser concreto y ejecutable.
  - Tipos permitidos:
      * "llm": un paso de razonamiento/generación con el LLM.
      * "tool": llamada a una herramienta (nombre exacto en `tool_name`).
      * "memory": recuperación de memoria del usuario.
      * "rag": recuperación de documentos del usuario.
      * "subplan": reservado para futuro (evítalo por ahora).
  - Usa `depends_on` para expresar dependencias (por id de otro paso).
  - Los `id` deben ser cortos, únicos y sin espacios: "s1", "s2"...
  - Si no necesitas herramientas, no las uses: puedes hacer un plan solo con `llm`.

Devuelve EXCLUSIVAMENTE un JSON con esta forma:

{
  "goal": "objetivo en una frase",
  "steps": [
    {"id": "s1", "kind": "llm", "description": "...", "depends_on": []},
    {"id": "s2", "kind": "llm", "description": "...", "depends_on": ["s1"]}
  ],
  "reasoning": "explicación breve de por qué este plan"
}
"""

# Longitud mínima aceptada por ExecutionPlan.goal.
_MIN_GOAL_LEN = 3
# Texto por defecto si el mensaje es demasiado corto (defensivo).
_DEFAULT_GOAL = "Tarea sin descripción"


class Planner:
    def __init__(self, llm: LLMProvider, *, max_steps: int = 6) -> None:
        self.llm = llm
        self.max_steps = max_steps

    async def plan(self, message: str, *, model: str | None = None) -> ExecutionPlan:
        """Genera un plan. Nunca lanza: si todo falla, devuelve plan degradado."""
        messages = [
            LLMMessage(role="system", content=PLANNER_SYSTEM_PROMPT),
            LLMMessage(role="user", content=message),
        ]

        for attempt in range(2):
            try:
                response = await self.llm.generate(
                    messages, model=model, temperature=0.0, max_tokens=1200
                )
            except Exception as exc:
                log.warning("planner_llm_failed", error=str(exc), attempt=attempt)
                continue

            plan = self._parse_and_validate(response.text or "")
            if plan is not None:
                return self._trim(plan)

            log.info("planner_invalid_json", attempt=attempt)

        # Fallback: plan degradado de un solo paso.
        # Usamos un goal saneado porque el mensaje puede ser muy corto (<3).
        return ExecutionPlan(
            goal=_safe_goal(message),
            steps=[
                PlanStep(
                    id="s1",
                    kind="llm",
                    description="Responder directamente al usuario",
                    depends_on=[],
                )
            ],
            reasoning="planner falló; se degrada a un único paso LLM",
        )

    # ------------------------------------------------------------------ #
    # Parsing y validación
    # ------------------------------------------------------------------ #
    def _parse_and_validate(self, raw: str) -> ExecutionPlan | None:
        payload = _extract_json(raw)
        if payload is None:
            return None

        # Recortamos a max_steps antes de validar (Pydantic valida max_length).
        steps_raw = payload.get("steps")
        if isinstance(steps_raw, list) and len(steps_raw) > self.max_steps:
            payload["steps"] = steps_raw[: self.max_steps]

        # Si el goal es demasiado corto, lo saneamos antes de que Pydantic falle.
        if isinstance(payload.get("goal"), str):
            payload["goal"] = _safe_goal(payload["goal"])

        try:
            return ExecutionPlan(**payload)
        except ValidationError as exc:
            log.info("planner_validation_failed", error=str(exc))
            return None

    def _trim(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Elimina dependencias hacia pasos que no existen (defensivo)."""
        existing_ids = {s.id for s in plan.steps}
        for step in plan.steps:
            step.depends_on = [d for d in step.depends_on if d in existing_ids]
        return plan


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _safe_goal(text: str) -> str:
    """Normaliza un goal para que cumpla min_length=3 sin romper el flujo."""
    cleaned = (text or "").strip()[:200]
    if len(cleaned) >= _MIN_GOAL_LEN:
        return cleaned
    return _DEFAULT_GOAL


def _extract_json(text: str) -> dict[str, Any] | None:
    # 1. Fence markdown
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Primer {...} balanceado
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    # 3. Todo el texto
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None