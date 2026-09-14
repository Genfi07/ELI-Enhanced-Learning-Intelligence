"""Tests del GoalDetector."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas.llm import LLMResponse, TokenUsage
from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.eli.goal_detector import (
    GoalDetector,
    has_topic_hints,
    should_run_detector,
)
from app.eli.goal_service import GoalService


# --------------------------------------------------------------------------- #
# FakeLLM controlable
# --------------------------------------------------------------------------- #
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
# has_topic_hints
# --------------------------------------------------------------------------- #
def test_has_topic_hints_detects_tech():
    assert has_topic_hints("Me gusta programar en Python") is True
    assert has_topic_hints("¿Cómo funciona una API REST?") is True
    assert has_topic_hints("Quiero aprender machine learning") is True


def test_has_topic_hints_on_greeting():
    assert has_topic_hints("Hola, ¿cómo estás?") is False
    assert has_topic_hints("Buenos días") is False
    assert has_topic_hints("Gracias por tu ayuda") is False


# --------------------------------------------------------------------------- #
# should_run_detector
# --------------------------------------------------------------------------- #
def test_should_run_on_many_turns():
    assert should_run_detector(message="hola", turns_since_last_detect=10) is True
    assert should_run_detector(message="hola", turns_since_last_detect=15) is True


def test_should_run_on_long_topic_message():
    long_msg = (
        "Estoy trabajando en un proyecto de Python con FastAPI y quiero "
        "entender cómo estructurar bien las dependencias entre módulos "
        "para evitar acoplamiento. También me interesa mejorar el manejo "
        "de errores en la capa de servicios."
    )
    assert len(long_msg) >= 200
    assert should_run_detector(message=long_msg, turns_since_last_detect=2) is True


def test_should_not_run_on_short_message():
    assert should_run_detector(message="hola", turns_since_last_detect=2) is False
    assert should_run_detector(
        message="gracias por tu ayuda", turns_since_last_detect=5
    ) is False


def test_should_not_run_on_long_message_without_topics():
    long_msg = (
        "Ayer fui al parque con mis amigos y estuvimos hablando durante "
        "mucho rato de cosas personales, no técnicas. Nos reímos bastante "
        "y lo pasamos muy bien. Después fuimos a cenar y volvimos a casa "
        "tarde pero contentos por haber compartido ese rato juntos."
    )
    assert len(long_msg) >= 200
    assert should_run_detector(message=long_msg, turns_since_last_detect=2) is False


# --------------------------------------------------------------------------- #
# maybe_create_goal con LLM simulado
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_detector_creates_goal_from_llm(session: AsyncSession):
    conv = Conversation(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        title="test",
    )
    session.add(conv)
    await session.flush()

    session.add(Message(conversation_id=conv.id, role="user", content="Me gusta Python"))
    session.add(Message(conversation_id=conv.id, role="assistant", content="Bien."))
    session.add(Message(conversation_id=conv.id, role="user", content="Quiero entender async"))
    await session.flush()

    llm = ScriptedLLM([
        '{"should_create": true, "kind": "LEARN", '
        '"content": "Entender asyncio en Python en producción", '
        '"priority": 4, "related_topics": ["python", "async"], '
        '"reason": "el usuario lo menciona repetidamente"}'
    ])

    detector = GoalDetector(session, llm)
    goal = await detector.maybe_create_goal(conversation_id=conv.id)

    assert goal is not None
    assert goal.kind == "LEARN"
    assert goal.origin == "DETECTED"
    assert goal.priority == 4
    assert "asyncio" in goal.content
    assert goal.source_conversation_id == conv.id


@pytest.mark.asyncio
async def test_detector_skips_when_llm_says_no(session: AsyncSession):
    conv = Conversation(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        title="test",
    )
    session.add(conv)
    await session.flush()
    session.add(Message(conversation_id=conv.id, role="user", content="Me gusta Python"))
    await session.flush()

    llm = ScriptedLLM([
        '{"should_create": false, "reason": "no hay tema recurrente"}'
    ])

    detector = GoalDetector(session, llm)
    goal = await detector.maybe_create_goal(conversation_id=conv.id)
    assert goal is None


@pytest.mark.asyncio
async def test_detector_deduplicates_similar_goals(session: AsyncSession):
    svc = GoalService(session)
    await svc.create_goal(
        kind="LEARN",
        content="Entender asyncio y concurrencia en Python",
        origin="DETECTED",
    )

    conv = Conversation(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        title="test",
    )
    session.add(conv)
    await session.flush()
    session.add(Message(conversation_id=conv.id, role="user", content="Python asyncio"))
    await session.flush()

    llm = ScriptedLLM([
        '{"should_create": true, "kind": "LEARN", '
        '"content": "Entender asyncio y concurrencia en Python", '
        '"priority": 4, "related_topics": ["python"], "reason": "..."}'
    ])

    detector = GoalDetector(session, llm)
    goal = await detector.maybe_create_goal(conversation_id=conv.id)

    assert goal is None