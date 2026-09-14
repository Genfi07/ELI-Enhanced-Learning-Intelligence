"""Tests del detector de propuestas de reglas."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eli_identity import EliRuleProposal
from app.eli.rule_proposal_detector import (
    RuleProposalDetector,
    _categorize,
    _extract_rule,
)


FATHER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# --------------------------------------------------------------------------- #
# _extract_rule (función pura)
# --------------------------------------------------------------------------- #
def test_extract_a_partir_de_ahora():
    r = _extract_rule("A partir de ahora, responde en español.")
    assert r is not None
    assert "español" in r


def test_extract_quiero_que():
    r = _extract_rule("Quiero que seas más concisa en tus respuestas.")
    assert r is not None
    assert "concis" in r.lower()


def test_extract_recuerda_que():
    r = _extract_rule("Recuerda que nunca debes adularme.")
    assert r is not None
    assert "adularme" in r


def test_extract_nueva_regla():
    r = _extract_rule("Nueva regla: cita fuentes cuando uses datos.")
    assert r is not None
    assert "cita fuentes" in r


def test_extract_rejects_question():
    """Las preguntas no son instrucciones."""
    assert _extract_rule("¿Qué opinas de que sea más corta?") is None
    assert _extract_rule("¿Podrías ser más honesta?") is None


def test_extract_rejects_hypothesis():
    """Frases hipotéticas no son instrucciones."""
    assert _extract_rule("Imagina que fuera más directa.") is None
    assert _extract_rule("Sería bueno si fueras más breve.") is None


def test_extract_rejects_short_rule():
    """Contenido demasiado corto no es una regla."""
    assert _extract_rule("A partir de ahora sí.") is None


def test_extract_rejects_greeting():
    assert _extract_rule("Hola, ¿cómo estás?") is None


# --------------------------------------------------------------------------- #
# _categorize (función pura)
# --------------------------------------------------------------------------- #
def test_categorize_style_by_language():
    assert _categorize("responde siempre en español") == "STYLE"


def test_categorize_style_by_length():
    assert _categorize("sé más concisa en tus respuestas") == "STYLE"
    assert _categorize("da respuestas breves") == "STYLE"


def test_categorize_tone():
    assert _categorize("usa un tono más cercano conmigo") == "TONE"
    assert _categorize("sé más cálida en el trato") == "TONE"


def test_categorize_autonomy():
    assert _categorize("tienes más autonomía para contradecirme") == "AUTONOMY"
    assert _categorize("puedes cuestionar mis premisas") == "AUTONOMY"


def test_categorize_value():
    assert _categorize("mantén tu honestidad siempre") == "VALUE"


def test_categorize_default_is_rule():
    assert _categorize("cita fuentes cuando uses datos") == "RULE"


# --------------------------------------------------------------------------- #
# RuleProposalDetector (con BD)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_detector_only_acts_for_father(session: AsyncSession):
    """Un usuario normal no puede proponer reglas."""
    detector = RuleProposalDetector(session)

    stranger_id = uuid.uuid4()
    result = await detector.detect_and_propose(
        user_id=stranger_id,
        conversation_id=None,
        message="A partir de ahora, responde en inglés.",
    )
    assert result is None

    # Y no se ha creado nada en BD
    from sqlalchemy import select
    rows = list((await session.scalars(select(EliRuleProposal))).all())
    assert rows == []


@pytest.mark.asyncio
async def test_detector_creates_proposal_for_father(session: AsyncSession):
    detector = RuleProposalDetector(session)

    result = await detector.detect_and_propose(
        user_id=FATHER_ID,
        conversation_id=None,
        message="A partir de ahora, responde siempre en español.",
    )
    assert result is not None
    assert result.status == "PENDING"
    assert result.category == "STYLE"
    assert "español" in result.content
    assert result.taught_by == FATHER_ID


@pytest.mark.asyncio
async def test_detector_ignores_regular_message(session: AsyncSession):
    """Un mensaje normal no crea propuesta."""
    detector = RuleProposalDetector(session)

    result = await detector.detect_and_propose(
        user_id=FATHER_ID,
        conversation_id=None,
        message="Hola, ¿cómo estás hoy?",
    )
    assert result is None


@pytest.mark.asyncio
async def test_get_pending_for_conversation(session: AsyncSession):
    from app.db.models.conversation import Conversation

    detector = RuleProposalDetector(session)

    # Creamos una conversación real para satisfacer la FK.
    conv = Conversation(
        user_id=FATHER_ID,
        title="test",
    )
    session.add(conv)
    await session.flush()

    proposal = await detector.detect_and_propose(
        user_id=FATHER_ID,
        conversation_id=conv.id,
        message="A partir de ahora, usa un tono más cercano.",
    )
    assert proposal is not None

    found = await detector.get_pending_for_conversation(conv.id)
    assert found is not None
    assert found.id == proposal.id