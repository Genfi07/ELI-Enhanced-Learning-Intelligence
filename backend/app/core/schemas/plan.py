"""Schemas del Decision Engine, Planner y Plan Executor."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

Route = Literal["FAST", "STANDARD", "DEEP"]
StepKind = Literal["llm", "tool", "memory", "rag", "subplan"]
StepStatus = Literal["pending", "running", "done", "failed", "skipped"]
ExecutionStatus = Literal["ok", "partial", "failed"]


class Budget(BaseModel):
    max_tokens: int = 16_000
    max_response_tokens: int = 1_024
    max_tool_calls: int = 0
    max_latency_ms: int = 30_000


class ProcessingPlan(BaseModel):
    route: Route
    needs_memory: bool = False
    needs_rag: bool = False
    needs_tools: bool = False
    needs_planning: bool = False
    needs_validation: bool = False
    allowed_tools: list[str] | None = None
    budget: Budget = Field(default_factory=Budget)

    def short(self) -> dict:
        return {
            "route": self.route,
            "needs_memory": self.needs_memory,
            "needs_rag": self.needs_rag,
            "needs_tools": self.needs_tools,
            "needs_planning": self.needs_planning,
            "needs_validation": self.needs_validation,
        }


# --------------------------------------------------------------------------- #
# Planner
# --------------------------------------------------------------------------- #
class PlanStep(BaseModel):
    """Un paso ejecutable dentro de un plan."""

    id: str = Field(min_length=1, max_length=40)
    kind: StepKind
    description: str = Field(min_length=3, max_length=500)
    depends_on: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    tool_arguments: dict | None = None


class ExecutionPlan(BaseModel):
    """Plan completo producido por el Planner."""

    goal: str = Field(min_length=3, max_length=500)
    steps: list[PlanStep] = Field(default_factory=list, max_length=12)
    reasoning: str | None = None


# --------------------------------------------------------------------------- #
# Plan Executor
# --------------------------------------------------------------------------- #
class StepResult(BaseModel):
    step_id: str
    kind: StepKind
    status: StepStatus
    output: str | None = None
    error: str | None = None
    latency_ms: int = 0
    # True si el paso fue un stub explícito de una fase no implementada.
    is_stub: bool = False


class ExecutionResult(BaseModel):
    goal: str
    status: ExecutionStatus
    step_results: list[StepResult] = Field(default_factory=list)
    # Texto acumulado de los outputs exitosos, listo para inyectar al LLM
    # de síntesis final.
    final_context: str = ""
    total_latency_ms: int = 0