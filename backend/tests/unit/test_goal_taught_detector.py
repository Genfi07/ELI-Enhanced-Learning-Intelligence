"""Tests del TaughtGoalDetector."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas.llm import LLMResponse, TokenUsage
from app.db.models.eli_goal import EliGoal
from app.eli.goal_taught_detector import (
    TaughtGoalDetector,
    _TAUGHT_PATTERNS,
)
from sqlalchemy import select


FATHER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ScriptedLLM:
    name = "scripted"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self._index = 0

    async def generate(self, messages, **kwargs) -> LLMResponse:
        text = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return LLMResponse(
            text=text,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            model="scripted",
        )

    async def stream(self, messages, **kwargs):
        if False:
            yield  # pragma: no cover
        raise NotImplementedError

    def count_tokens(self, messages) -> int:
        return 0


# --------------------------------------------------------------------------- #
# Pre-filtro (regex)
# --------------------------------------------------------------------------- #
def test_taught_pattern_matches_aprende():
    assert _TAUGHT_PATTERNS.search("Aprende sobre Python asincrónico")


def test_taught_pattern_matches_quiero_que_explores():
    assert _TAUGHT_PATTERNS.search("Quiero que explores el tema de embeddings")


def test_taught_pattern_matches_nueva_meta():
    assert _TAUGHT_PATTERNS.search("Nueva meta: aprender Rust")


def test_taught_pattern_does_not_match_greeting():
    assert not _TAUGHT_PATTERNS.search("Hola, ¿cómo estás?")


# --------------------------------------------------------------------------- #
# Flujo completo con LLM scripted
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_taught_goal_created_for_father(session: AsyncSession):
    llm = ScriptedLLM([
        '{"kind": "LEARN", "content": "Entender Rust y su modelo de ownership", '
        '"priority": 4, "related_topics": ["rust", "systems"]}'
    ])
    detector = TaughtGoalDetector(session, llm)
    goal = await detector.maybe_create_taught_goal(
        user_id=FATHER_ID,
        conversation_id=None,
        message="Aprende sobre Rust",
    )
    assert goal is not None
    assert goal.kind == "LEARN"
    assert goal.origin == "TAUGHT"
    assert goal.priority == 4


@pytest.mark.asyncio
async def test_taught_goal_skipped_for_non_father(session: AsyncSession):
    llm = ScriptedLLM([
        '{"kind": "LEARN", "content": "X", "priority": 3}'
    ])
    detector = TaughtGoalDetector(session, llm)
    goal = await detector.maybe_create_taught_goal(
        user_id=uuid.uuid4(),  # usuario aleatorio, no padre
        conversation_id=None,
        message="Aprende sobre Rust",
    )
    assert goal is None


@pytest.mark.asyncio
async def test_taught_goal_skipped_without_pattern(session: AsyncSession):
    llm = ScriptedLLM(['{"kind": null}'])
    detector = TaughtGoalDetector(session, llm)
    goal = await detector.maybe_create_taught_goal(
        user_id=FATHER_ID,
        conversation_id=None,
        message="Hola ELI, ¿cómo estás?",
    )
    assert goal is None


@pytest.mark.asyncio
async def test_taught_goal_skipped_when_llm_returns_null(session: AsyncSession):
    llm = ScriptedLLM(['{"kind": null}'])
    detector = TaughtGoalDetector(session, llm)
    goal = await detector.maybe_create_taught_goal(
        user_id=FATHER_ID,
        conversation_id=None,
        message="Aprende",  # sin objeto, aunque matchee el patrón
    )
    assert goal is None


@pytest.mark.asyncio
async def test_taught_goal_persists_with_correct_origin(session: AsyncSession):
    llm = ScriptedLLM([
        '{"kind": "EXPLORE", "content": "Investigar embeddings multilingües", '
        '"priority": 5, "related_topics": ["embeddings", "nlp"]}'
    ])
    detector = TaughtGoalDetector(session, llm)
    await detector.maybe_create_taught_goal(
        user_id=FATHER_ID,
        conversation_id=None,
        message="Quiero que explores embeddings multilingües",
    )

    rows = list((await session.scalars(select(EliGoal))).all())
    assert len(rows) == 1
    assert rows[0].origin == "TAUGHT"
    assert rows[0].kind == "EXPLORE"