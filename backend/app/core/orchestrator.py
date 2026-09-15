"""Orquestador de turno.

Pipeline:
  FAST / STANDARD:
    user_message → (confirmation) → (proposal) → (taught_goal)
                 → (identity) → (state) → (datetime) → (goals)
                 → (attached_documents) → (web_search)
                 → (summary) → (memory) → (rag)
                 → build_context → llm_stream → persist → final
                 → tick_state → goal_detector → memory_extraction

  DEEP:
    igual pero además → planner → executor → synthesis

Orden de bloques del system prompt (de más a menos prioritario):
  1. confirmation_block    (respuesta a una confirmación del usuario)
  2. pending_proposal_block (pedir confirmación de una regla)
  3. identity              (núcleo inmutable + axioms + reglas)
  4. state                 (ánimo, energía, foco, curiosidad)
  5. current_datetime      (solo si la pregunta es de hora/fecha)
  6. goals                 (metas activas de ELI)
  7. attached_documents    (docs adjuntos por el usuario) ← ALTA PRIORIDAD
  8. web_search_results    (solo si la pregunta requiere actualidad)
  9. summary + memory      (resumen de conversación + memorias del usuario)
 10. documents (RAG)       (búsqueda general sobre todos los docs activos)
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.config.settings import get_settings
from app.core.datetime_context import (
    build_datetime_block,
    should_inject_datetime,
)
from app.core.web_search_trigger import (
    extract_search_query,
    format_search_results,
    should_search_web,
)
from app.eli.identity_service import IdentityService
from app.eli.rule_confirmation import RuleConfirmationProcessor
from app.eli.rule_proposal_detector import RuleProposalDetector
from app.eli.state_service import StateService
from app.eli.goal_detector import should_run_detector, schedule_detection
from app.eli.goal_taught_detector import TaughtGoalDetector
from app.eli.goal_service import GoalService
from app.core.context_builder import ContextBuilder
from app.core.decision_engine import DecisionEngine
from app.core.intent_classifier import HybridIntentClassifier
from app.core.plan_executor import PlanExecutor
from app.core.planner import Planner
from app.core.schemas.plan import ProcessingPlan
from app.core.schemas.turn import TurnRequest
from app.db.models.user import User
from app.db.session import session_scope
from app.llm.router import ModelRouter
from app.memory.service import MemoryService
from app.observability.logging import get_logger
from app.observability.tracing import TraceBuilder
from app.rag.service import KnowledgeService
from app.repositories.conversations import ConversationRepository
from app.repositories.messages import MessageRepository
from app.repositories.traces import TraceRepository

log = get_logger(__name__)


class Orchestrator:
    def __init__(
        self,
        model_router: ModelRouter,
        decision_engine: DecisionEngine | None = None,
        context_builder: ContextBuilder | None = None,
        memory: MemoryService | None = None,
        knowledge: KnowledgeService | None = None,
        classifier: HybridIntentClassifier | None = None,
        planner: Planner | None = None,
        executor: PlanExecutor | None = None,
    ) -> None:
        self.model_router = model_router
        self.decision_engine = decision_engine or DecisionEngine()
        self.context_builder = context_builder or ContextBuilder()
        self.memory = memory
        self.knowledge = knowledge
        self.classifier = classifier
        self.planner = planner
        self.executor = executor
        self.provider = model_router.provider

    async def _resolve_plan(self, message: str) -> ProcessingPlan:
        if self.classifier is not None:
            return await self.classifier.classify(message)
        return self.decision_engine.plan_for(message)

    async def run_stream(self, req: TurnRequest) -> AsyncIterator[dict]:
        settings = get_settings()
        plan = await self._resolve_plan(req.message)
        trace = TraceBuilder(
            user_id=req.user_id,
            conversation_id=req.conversation_id,
            route=plan.route,
            plan=plan.short(),
        )
        memory_used = 0
        rag_used = 0
        attached_chunks_used = 0
        planned = False
        plan_steps = 0
        plan_status: str | None = None

        try:
            async with session_scope() as session:
                conv_repo = ConversationRepository(session)
                msg_repo = MessageRepository(session)

                # ---------------------------------------------------- #
                # Cargar conversación y persistir mensaje del usuario
                # ---------------------------------------------------- #
                async with trace.step("load_conversation") as s:
                    conv = await conv_repo.get_for_user(
                        req.user_id, req.conversation_id
                    )
                    if conv is None:
                        raise LookupError("conversation not found for user")
                    history = await msg_repo.recent_for_conversation(
                        conv.id, limit=settings.history_recent_messages
                    )
                    user_msg = await msg_repo.add(conv.id, "user", req.message)
                    s["meta"]["history_size"] = len(history)
                    s["meta"]["attached_docs"] = len(req.attached_document_ids)

                user = await session.get(User, req.user_id)

                yield {
                    "type": "meta",
                    "request_id": trace.request_id,
                    "route": plan.route,
                    "conversation_id": str(conv.id),
                    "user_message_id": str(user_msg.id),
                }

                # ---------------------------------------------------- #
                # 0.a) Confirmación de propuesta pendiente
                # ---------------------------------------------------- #
                confirmation_block: str | None = None
                async with trace.step("check_rule_confirmation") as s:
                    try:
                        processor = RuleConfirmationProcessor(session)
                        result = await processor.maybe_process(
                            user_id=req.user_id,
                            conversation_id=conv.id,
                            message=req.message,
                        )
                        if result is not None:
                            s["meta"]["decision"] = result["decision"]
                            s["meta"]["proposal_id"] = result["proposal_id"]
                            if "rule_id" in result:
                                s["meta"]["rule_id"] = result["rule_id"]
                            confirmation_block = result["block"]

                            yield {
                                "type": f"rule_proposal_{result['decision']}ed",
                                "proposal_id": result["proposal_id"],
                                "rule_id": result.get("rule_id"),
                                "category": result.get("category"),
                            }
                    except Exception as exc:
                        log.warning(
                            "rule_confirmation_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )
                        s["meta"]["error"] = str(exc)

                # ---------------------------------------------------- #
                # 0.b) Detectar propuesta de regla nueva
                # ---------------------------------------------------- #
                pending_proposal_block: str | None = None
                async with trace.step("detect_rule_proposal") as s:
                    try:
                        detector = RuleProposalDetector(session)
                        proposal = await detector.detect_and_propose(
                            user_id=req.user_id,
                            conversation_id=conv.id,
                            message=req.message,
                        )
                        if proposal is not None:
                            s["meta"]["proposal_id"] = str(proposal.id)
                            s["meta"]["category"] = proposal.category

                            pending_proposal_block = (
                                "<pending_rule_proposal>\n"
                                f"Categoría: {proposal.category}\n"
                                f"Contenido: {proposal.content}\n"
                                "INSTRUCCIÓN: Al final de tu respuesta, "
                                "menciona esta propuesta con naturalidad "
                                "y pregunta a tu padre si debe guardarla "
                                "como regla de comportamiento. No la "
                                "apliques todavía; espera su confirmación.\n"
                                "</pending_rule_proposal>"
                            )

                            yield {
                                "type": "rule_proposal_created",
                                "proposal_id": str(proposal.id),
                                "category": proposal.category,
                                "content": proposal.content,
                            }
                    except Exception as exc:
                        log.warning(
                            "rule_proposal_detection_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )
                        s["meta"]["error"] = str(exc)

                # ---------------------------------------------------- #
                # 0.c) Detectar meta enseñada explícitamente
                # ---------------------------------------------------- #
                async with trace.step("detect_taught_goal") as s:
                    try:
                        taught_detector = TaughtGoalDetector(session, self.provider)
                        taught_goal = await taught_detector.maybe_create_taught_goal(
                            user_id=req.user_id,
                            conversation_id=conv.id,
                            message=req.message,
                        )
                        if taught_goal is not None:
                            s["meta"]["goal_id"] = str(taught_goal.id)
                            s["meta"]["kind"] = taught_goal.kind
                            yield {
                                "type": "goal_created",
                                "goal_id": str(taught_goal.id),
                                "kind": taught_goal.kind,
                                "content": taught_goal.content,
                                "origin": "TAUGHT",
                            }
                    except Exception as exc:
                        log.warning(
                            "taught_goal_detection_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )
                        s["meta"]["error"] = str(exc)

                # ---------------------------------------------------- #
                # 1) Bloques de contexto (en orden de prioridad)
                # ---------------------------------------------------- #
                extra_blocks: list[str] = []

                # 1.0) Bloques de alta prioridad (respuesta inmediata)
                if confirmation_block:
                    extra_blocks.append(confirmation_block)
                if pending_proposal_block:
                    extra_blocks.append(pending_proposal_block)

                # 1.a) Identidad
                async with trace.step("load_identity") as s:
                    try:
                        identity_service = IdentityService(session)
                        identity_block = await identity_service.build_identity_block(
                            req.user_id
                        )
                        if identity_block:
                            extra_blocks.append(identity_block)
                            s["meta"]["identity_loaded"] = True
                        else:
                            s["meta"]["identity_loaded"] = False
                    except Exception as exc:
                        log.warning(
                            "identity_load_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )
                        s["meta"]["identity_error"] = str(exc)

                # 1.b) Estado interno
                async with trace.step("load_state") as s:
                    try:
                        state_service = StateService(session, self.provider)
                        state_block = await state_service.build_state_block()
                        extra_blocks.append(state_block)
                        state = await state_service.get_state()
                        s["meta"]["mood"] = state.mood
                        s["meta"]["energy"] = round(state.energy, 2)
                        s["meta"]["focus"] = round(state.focus, 2)
                        s["meta"]["curiosity"] = round(state.curiosity, 2)
                    except Exception as exc:
                        log.warning(
                            "state_load_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )
                        s["meta"]["state_error"] = str(exc)

                # 1.c) Contexto temporal (solo si la pregunta lo pide)
                if should_inject_datetime(req.message):
                    extra_blocks.append(build_datetime_block())

                # 1.d) Metas propias de ELI
                async with trace.step("load_goals") as s:
                    try:
                        goal_service = GoalService(session)
                        goals_block = await goal_service.build_goals_block()
                        if goals_block:
                            extra_blocks.append(goals_block)
                        active_count = await goal_service.count_active()
                        s["meta"]["active_goals"] = active_count
                    except Exception as exc:
                        log.warning(
                            "goals_load_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )
                        s["meta"]["goals_error"] = str(exc)

                # 1.e) Documentos adjuntos explícitamente (ALTA PRIORIDAD)
                if req.attached_document_ids and self.knowledge is not None:
                    async with trace.step("load_attached_documents") as s:
                        try:
                            attached_ctx = (
                                await self.knowledge.retrieve_attached_context(
                                    session,
                                    req.user_id,
                                    req.attached_document_ids,
                                    query=req.message,
                                )
                            )
                            if attached_ctx is not None:
                                extra_blocks.append(attached_ctx.text)
                                attached_chunks_used = len(attached_ctx.chunk_ids)
                                s["meta"]["chunks"] = attached_chunks_used
                                s["meta"]["docs"] = attached_ctx.document_titles
                            else:
                                s["meta"]["no_content"] = True
                        except Exception as exc:
                            log.warning(
                                "attached_documents_load_failed",
                                request_id=trace.request_id,
                                error=str(exc),
                            )
                            s["meta"]["error"] = str(exc)

                # 1.f) Búsqueda web (solo si la pregunta lo pide)
                if should_search_web(req.message):
                    async with trace.step("web_search") as s:
                        try:
                            query = extract_search_query(req.message)
                            s["meta"]["query"] = query

                            runtime = (
                                self.executor.tool_runtime
                                if self.executor is not None
                                else None
                            )
                            if runtime is None or user is None:
                                s["meta"]["skipped"] = "sin runtime o user"
                            else:
                                from app.tools.runtime import ToolInvocationContext
                                ctx = ToolInvocationContext(
                                    user_id=req.user_id,
                                    conversation_id=conv.id,
                                    message_id=user_msg.id,
                                )
                                result = await runtime.invoke(
                                    session,
                                    user=user,
                                    tool_name="web_search",
                                    arguments={"query": query, "max_results": 5},
                                    context=ctx,
                                )
                                s["meta"]["status"] = result.status
                                s["meta"]["latency_ms"] = result.latency_ms

                                if result.status == "OK":
                                    block = format_search_results(result.result)
                                    extra_blocks.append(block)
                                    s["meta"]["results"] = (
                                        result.result or {}
                                    ).get("count", 0)
                                else:
                                    block = format_search_results(
                                        None, error=result.error or result.status
                                    )
                                    extra_blocks.append(block)
                        except Exception as exc:
                            log.warning(
                                "web_search_failed",
                                request_id=trace.request_id,
                                error=str(exc),
                            )
                            s["meta"]["error"] = str(exc)

                # 1.g) Resumen de conversación + memoria
                if self.memory is not None:
                    summary_block = self.memory.conversation_summary_block(conv.meta)
                    if summary_block:
                        extra_blocks.append(summary_block)

                    async with trace.step("retrieve_memory") as s:
                        try:
                            mem_ctx = await self.memory.retrieve_context(
                                session, req.user_id, req.message
                            )
                            if mem_ctx is not None:
                                extra_blocks.append(mem_ctx.text)
                                memory_used = len(mem_ctx.memory_ids)
                                s["meta"]["memory_count"] = memory_used
                        except Exception as exc:
                            log.warning(
                                "memory_retrieve_failed",
                                request_id=trace.request_id,
                                error=str(exc),
                            )
                            s["meta"]["memory_error"] = str(exc)

                # 1.h) RAG general (solo si el plan lo pide)
                if plan.needs_rag and self.knowledge is not None:
                    async with trace.step("retrieve_rag") as s:
                        try:
                            rag_ctx = await self.knowledge.retrieve_context(
                                session, req.user_id, req.message
                            )
                            if rag_ctx is not None:
                                extra_blocks.append(rag_ctx.text)
                                rag_used = len(rag_ctx.chunk_ids)
                                s["meta"]["rag_chunks"] = rag_used
                                s["meta"]["rag_docs"] = rag_ctx.document_titles
                        except Exception as exc:
                            log.warning(
                                "rag_retrieve_failed",
                                request_id=trace.request_id,
                                error=str(exc),
                            )
                            s["meta"]["rag_error"] = str(exc)

                # ---------------------------------------------------- #
                # 2) Planificación y ejecución (DEEP)
                # ---------------------------------------------------- #
                model = self.model_router.model_for(plan.route)
                synthesis_blocks = list(extra_blocks)

                if (
                    plan.needs_planning
                    and settings.planning_enabled
                    and self.planner is not None
                    and self.executor is not None
                ):
                    execution_plan = None
                    exec_result = None

                    async with trace.step("plan") as s:
                        try:
                            execution_plan = await self.planner.plan(
                                req.message, model=model
                            )
                            planned = True
                            plan_steps = len(execution_plan.steps)
                            s["meta"]["steps"] = plan_steps
                            s["meta"]["goal"] = execution_plan.goal
                        except Exception as exc:
                            log.warning(
                                "planner_failed",
                                request_id=trace.request_id,
                                error=str(exc),
                            )
                            s["meta"]["planner_error"] = str(exc)

                    if execution_plan is not None:
                        yield {
                            "type": "plan_created",
                            "goal": execution_plan.goal,
                            "steps": [
                                {
                                    "id": st.id,
                                    "kind": st.kind,
                                    "description": st.description,
                                }
                                for st in execution_plan.steps
                            ],
                        }

                        async with trace.step("execute_plan") as s:
                            try:
                                exec_result = await self.executor.execute(
                                    execution_plan,
                                    user_message=req.message,
                                    model=model,
                                    session=session,
                                    user=user,
                                    conversation_id=conv.id,
                                )
                                plan_status = exec_result.status
                                done_count = sum(
                                    1
                                    for r in exec_result.step_results
                                    if r.status == "done"
                                )
                                s["meta"]["status"] = plan_status
                                s["meta"]["done_steps"] = done_count
                            except Exception as exc:
                                log.warning(
                                    "executor_failed",
                                    request_id=trace.request_id,
                                    error=str(exc),
                                )
                                s["meta"]["executor_error"] = str(exc)
                                plan_status = "failed"

                        if exec_result is not None and exec_result.final_context:
                            synthesis_blocks.append(
                                "RESULTADO DE LOS PASOS PREVIOS:\n"
                                + exec_result.final_context
                            )
                            yield {
                                "type": "plan_executed",
                                "status": plan_status,
                                "steps": [
                                    {
                                        "id": r.step_id,
                                        "kind": r.kind,
                                        "status": r.status,
                                    }
                                    for r in exec_result.step_results
                                ],
                            }

                # ---------------------------------------------------- #
                # 3) Construir contexto
                # ---------------------------------------------------- #
                async with trace.step("build_context") as s:
                    messages = self.context_builder.build(
                        history, req.message, extra_system_blocks=synthesis_blocks
                    )
                    s["meta"]["messages_sent"] = len(messages)
                    s["meta"]["planned"] = planned

                # ---------------------------------------------------- #
                # 4) Streaming
                # ---------------------------------------------------- #
                chunks: list[str] = []
                usage = None
                async with trace.step("llm_stream", model=model):
                    try:
                        async for chunk in self.provider.stream(  # type: ignore[attr-defined]
                            messages, model=model
                        ):
                            if chunk.is_final:
                                usage = chunk.usage
                                break
                            chunks.append(chunk.delta)
                            yield {"type": "token", "delta": chunk.delta}
                    except Exception as exc:
                        log.exception(
                            "llm_stream_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )
                        yield {"type": "error", "message": "Fallo del proveedor LLM"}
                        return

                final_text = "".join(chunks)

                # ---------------------------------------------------- #
                # 5) Persistir assistant
                # ---------------------------------------------------- #
                async with trace.step("persist_assistant") as s:
                    assistant_msg = await msg_repo.add(
                        conv.id,
                        "assistant",
                        final_text,
                        tokens_in=usage.prompt_tokens if usage else 0,
                        tokens_out=usage.completion_tokens if usage else 0,
                        model=model,
                        request_id=trace.request_id,
                    )
                    if not conv.title or conv.title == "Nueva conversación":
                        conv.title = (
                            final_text[:60] or "Nueva conversación"
                        ).strip()
                    s["meta"]["assistant_message_id"] = str(assistant_msg.id)

                # ---------------------------------------------------- #
                # 6) Evento final
                # ---------------------------------------------------- #
                final_event: dict = {
                    "type": "final",
                    "assistant_message_id": str(assistant_msg.id),
                    "route": plan.route,
                    "usage": {
                        "prompt_tokens": usage.prompt_tokens if usage else 0,
                        "completion_tokens": usage.completion_tokens if usage else 0,
                        "total_tokens": usage.total_tokens if usage else 0,
                    },
                    "memory_used": memory_used,
                    "rag_used": rag_used,
                    "attached_chunks_used": attached_chunks_used,
                }
                if planned:
                    final_event["planned"] = True
                    final_event["plan_steps"] = plan_steps
                    final_event["plan_status"] = plan_status
                yield final_event

                # ---------------------------------------------------- #
                # 7) Tareas de fondo (async, no bloquean la respuesta)
                # ---------------------------------------------------- #
                # 7.a) Tick del estado interno
                async with trace.step("tick_state") as s:
                    try:
                        state_service = StateService(session, self.provider)
                        await state_service.tick_and_maybe_update(conv.id)
                        state = await state_service.get_state()
                        s["meta"]["turns_since_update"] = state.turns_since_update
                    except Exception as exc:
                        log.warning(
                            "state_tick_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )

                # 7.b) Detector de metas propias (cada 10 turnos o mensaje largo)
                async with trace.step("maybe_detect_goal") as s:
                    try:
                        meta = dict(conv.meta or {})
                        turns = int(meta.get("turns_since_goal_detect", 0)) + 1

                        if should_run_detector(
                            message=req.message,
                            turns_since_last_detect=turns,
                        ):
                            s["meta"]["triggered"] = True
                            s["meta"]["turns_accumulated"] = turns
                            meta["turns_since_goal_detect"] = 0
                            schedule_detection(self.provider, conv.id)
                        else:
                            s["meta"]["triggered"] = False
                            s["meta"]["turns_accumulated"] = turns
                            meta["turns_since_goal_detect"] = turns

                        conv.meta = meta
                    except Exception as exc:
                        log.warning(
                            "goal_detect_schedule_failed",
                            request_id=trace.request_id,
                            error=str(exc),
                        )
                        s["meta"]["error"] = str(exc)

                # 7.c) Extracción de memoria y summarización
                if self.memory is not None:
                    self.memory.schedule_extraction(
                        user_id=req.user_id,
                        conversation_id=conv.id,
                        user_message=req.message,
                        assistant_message=final_text,
                    )
                    self.memory.schedule_summarization(
                        user_id=req.user_id,
                        conversation_id=conv.id,
                    )
        finally:
            await self._persist_trace(trace)

    async def _persist_trace(self, trace: TraceBuilder) -> None:
        if not get_settings().trace_enabled:
            return
        try:
            async with session_scope() as s:
                await TraceRepository(s).record(trace.to_trace())
        except Exception:
            log.exception("trace_persist_failed", request_id=trace.request_id)