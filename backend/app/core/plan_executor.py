"""PlanExecutor: ejecuta un ExecutionPlan paso a paso.

Diseño:
  - Ejecución secuencial con orden topológico (dependencias primero).
  - Política de errores: un paso `failed` propaga skip a sus dependientes;
    un paso `skipped` (por stub de fase futura) NO bloquea a los demás.
  - Los pasos `tool` invocan herramientas reales vía ToolRuntime (Fase 6).
  - Los pasos `rag` y `memory` devuelven stubs (la memoria y el RAG se
    recuperan antes del plan, no como pasos).
  - El executor NUNCA lanza: cualquier error se captura y se refleja en el
    StepResult. El orquestador puede seguir con la síntesis final.
  - Presupuesto acotado: tokens por paso y chars máximos de final_context.
"""
from __future__ import annotations

import time
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts.llm import LLMProvider
from app.core.schemas.llm import LLMMessage
from app.core.schemas.plan import (
    ExecutionPlan,
    ExecutionResult,
    PlanStep,
    StepResult,
)
from app.db.models.user import User
from app.observability.logging import get_logger

log = get_logger(__name__)

DEFAULT_STEP_MAX_TOKENS = 800
DEFAULT_FINAL_CONTEXT_CHARS = 8_000


STEP_SYSTEM_PROMPT = """\
Eres ELI ejecutando un paso concreto de un plan de trabajo. Te doy el objetivo
global, el paso actual y cualquier output de pasos anteriores que necesites.

Reglas:
  - Responde SOLO con el contenido de este paso. No resumas todo el plan.
  - Sé conciso: máximo ~150 palabras.
  - No saludes ni cierres: es un paso intermedio, no la respuesta final.
  - Si el paso requiere información que no tienes, dilo explícitamente.
"""


class PlanExecutor:
    def __init__(
        self,
        llm: LLMProvider,
        *,
        step_max_tokens: int = DEFAULT_STEP_MAX_TOKENS,
        final_context_chars: int = DEFAULT_FINAL_CONTEXT_CHARS,
        tool_runtime: Any | None = None,
    ) -> None:
        self.llm = llm
        self.step_max_tokens = step_max_tokens
        self.final_context_chars = final_context_chars
        # Si se inyecta, los pasos `tool` invocan herramientas reales.
        # Si no, se devuelve un stub "skipped" (compatibilidad con tests
        # anteriores y con la fase en la que aún no había runtime).
        self.tool_runtime = tool_runtime

    async def execute(
        self,
        plan: ExecutionPlan,
        *,
        user_message: str,
        model: str | None = None,
        # Contexto opcional para pasos tipo `tool`: si no se pasa, los pasos
        # tool caen al stub (comportamiento anterior).
        session: AsyncSession | None = None,
        user: User | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> ExecutionResult:
        started = time.perf_counter()

        ordered = _topological_order(plan.steps)
        results: dict[str, StepResult] = {}

        for step in ordered:
            dep_statuses = {d: results.get(d) for d in step.depends_on}
            if any(r is None or r.status == "failed" for r in dep_statuses.values()):
                results[step.id] = StepResult(
                    step_id=step.id,
                    kind=step.kind,
                    status="skipped",
                    error="dependencia falló o no existe",
                )
                continue

            try:
                result = await self._run_step(
                    step,
                    user_message,
                    results,
                    model,
                    session=session,
                    user=user,
                    conversation_id=conversation_id,
                )
            except Exception as exc:
                log.warning(
                    "plan_step_exception",
                    step_id=step.id,
                    kind=step.kind,
                    error=str(exc),
                )
                result = StepResult(
                    step_id=step.id,
                    kind=step.kind,
                    status="failed",
                    error=str(exc),
                )
            results[step.id] = result

        all_results = [results[s.id] for s in ordered]
        done = [r for r in all_results if r.status == "done"]
        failed = [r for r in all_results if r.status == "failed"]
        if not all_results:
            global_status = "failed"
        elif not failed and done:
            global_status = "ok"
        elif done:
            global_status = "partial"
        else:
            global_status = "failed"

        final_context = _build_final_context(all_results, self.final_context_chars)

        total_ms = int((time.perf_counter() - started) * 1000)
        return ExecutionResult(
            goal=plan.goal,
            status=global_status,
            step_results=all_results,
            final_context=final_context,
            total_latency_ms=total_ms,
        )

    # ------------------------------------------------------------------ #
    # Despacho por tipo de paso
    # ------------------------------------------------------------------ #
    async def _run_step(
        self,
        step: PlanStep,
        user_message: str,
        prior: dict[str, StepResult],
        model: str | None,
        *,
        session: AsyncSession | None,
        user: User | None,
        conversation_id: uuid.UUID | None,
    ) -> StepResult:
        if step.kind == "llm":
            return await self._run_llm_step(step, user_message, prior, model)

        if step.kind == "tool":
            if (
                self.tool_runtime is not None
                and session is not None
                and user is not None
                and step.tool_name
            ):
                return await self._run_tool_step(
                    step, session=session, user=user, conversation_id=conversation_id
                )
            return _stub(step, "tool sin contexto o runtime inyectado")

        if step.kind == "rag":
            return _stub(step, "RAG se recupera antes del plan")
        if step.kind == "memory":
            return _stub(step, "la memoria se recupera antes del plan")
        return _stub(step, f"kind '{step.kind}' no soportado")

    async def _run_llm_step(
        self,
        step: PlanStep,
        user_message: str,
        prior: dict[str, StepResult],
        model: str | None,
    ) -> StepResult:
        started = time.perf_counter()

        dep_outputs = []
        for dep_id in step.depends_on:
            r = prior.get(dep_id)
            if r and r.output:
                dep_outputs.append(f"[{dep_id}] {r.output}")

        user_parts = [
            f"OBJETIVO GLOBAL:\n{user_message}",
            f"PASO A EJECUTAR ({step.id}):\n{step.description}",
        ]
        if dep_outputs:
            user_parts.append(
                "OUTPUTS DE PASOS ANTERIORES:\n" + "\n\n".join(dep_outputs)
            )

        messages = [
            LLMMessage(role="system", content=STEP_SYSTEM_PROMPT),
            LLMMessage(role="user", content="\n\n".join(user_parts)),
        ]

        response = await self.llm.generate(
            messages, model=model, temperature=0.3, max_tokens=self.step_max_tokens
        )
        text = (response.text or "").strip()
        latency = int((time.perf_counter() - started) * 1000)

        if not text:
            return StepResult(
                step_id=step.id,
                kind=step.kind,
                status="failed",
                error="respuesta vacía del LLM",
                latency_ms=latency,
            )

        return StepResult(
            step_id=step.id,
            kind=step.kind,
            status="done",
            output=text,
            latency_ms=latency,
        )

    async def _run_tool_step(
        self,
        step: PlanStep,
        *,
        session: AsyncSession,
        user: User,
        conversation_id: uuid.UUID | None,
    ) -> StepResult:
        from app.tools.runtime import ToolInvocationContext

        started = time.perf_counter()
        ctx = ToolInvocationContext(
            user_id=user.id,
            conversation_id=conversation_id,
            message_id=None,
        )
        result = await self.tool_runtime.invoke(
            session,
            user=user,
            tool_name=step.tool_name or "",
            arguments=step.tool_arguments or {},
            context=ctx,
        )
        latency = int((time.perf_counter() - started) * 1000)

        if result.status == "OK":
            # Serializamos el resultado para pasarlo al siguiente paso.
            import json
            try:
                output = json.dumps(result.result, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                output = str(result.result)
            return StepResult(
                step_id=step.id,
                kind="tool",
                status="done",
                output=output,
                latency_ms=latency,
            )

        if result.status == "PENDING_CONFIRMATION":
            return StepResult(
                step_id=step.id,
                kind="tool",
                status="skipped",
                error=(
                    f"tool '{step.tool_name}' requiere confirmación; "
                    "el usuario debe aprobarla por separado"
                ),
                latency_ms=latency,
            )

        return StepResult(
            step_id=step.id,
            kind="tool",
            status="failed",
            error=result.error or f"tool status={result.status}",
            latency_ms=latency,
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _stub(step: PlanStep, reason: str) -> StepResult:
    return StepResult(
        step_id=step.id,
        kind=step.kind,
        status="skipped",
        error=reason,
        is_stub=True,
    )


def _topological_order(steps: list[PlanStep]) -> list[PlanStep]:
    by_id = {s.id: s for s in steps}
    indegree: dict[str, int] = {s.id: 0 for s in steps}
    edges: dict[str, list[str]] = defaultdict(list)

    for s in steps:
        for dep in s.depends_on:
            if dep not in by_id:
                continue
            edges[dep].append(s.id)
            indegree[s.id] += 1

    order_index = {s.id: i for i, s in enumerate(steps)}
    queue = [sid for sid, deg in indegree.items() if deg == 0]
    queue.sort(key=lambda sid: order_index[sid])

    ordered: list[str] = []
    while queue:
        sid = queue.pop(0)
        ordered.append(sid)
        for nxt in edges.get(sid, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
        queue.sort(key=lambda sid: order_index[sid])

    for s in steps:
        if s.id not in ordered:
            ordered.append(s.id)

    return [by_id[sid] for sid in ordered]


def _build_final_context(results: list[StepResult], max_chars: int) -> str:
    parts: list[str] = []
    total = 0
    for r in results:
        if r.status != "done" or not r.output:
            continue
        piece = f"[{r.step_id}] {r.output}"
        if total + len(piece) > max_chars:
            continue
        parts.append(piece)
        total += len(piece) + 2
    return "\n\n".join(parts)