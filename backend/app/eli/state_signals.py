"""StateCalculator: extrae señales de la conversación reciente.

Función pura. No toca BD, no llama al LLM, no hace IO.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.models.message import Message


@dataclass
class ConversationSignals:
    turns_count: int
    user_messages_count: int
    avg_user_msg_length: float
    avg_assistant_msg_length: float
    minutes_since_last_interaction: int
    topic_variety: float
    is_technical: bool
    has_humor: bool
    is_long_conversation: bool
    user_seems_tired: bool
    signal_summary: str


_LONG_CONVERSATION_TURNS = 20
_SHORT_MSG_LEN = 25

_TECHNICAL_RE = re.compile(
    r"```|def |class |import |function |const |SELECT |INSERT |"
    r"\.py\b|\.ts\b|\.js\b|\.java\b|\.go\b|"
    r"https?://|Traceback|Exception|Error:|git |docker |"
    r"async |await |yield |return |"
    r"\bSQL\b|\bAPI\b|\bHTTP\b|\bJSON\b|\bREST\b|\bLLM\b",
    re.IGNORECASE,
)

_HUMOR_RE = re.compile(
    r"jaja|jeje|jiji|😂|🤣|😅|😆|😉|:\)|:D|"
    r"\bchiste\b|\bgracioso\b|\bc[óo]mico\b|\bbroma\b",
    re.IGNORECASE,
)

_TIRED_RE = re.compile(
    r"\bcansad[oa]\b|\bagotad[oa]\b|\bestoy\s+fundid[oa]\b|"
    r"\bno\s+puedo\s+m[áa]s\b|\bdormir\b|\bsue[ñn]o\b|"
    r"\bm[áa]s\s+tarde\b|\bma[ñn]ana\b",
    re.IGNORECASE,
)


def _count_unique_words(texts: list[str]) -> float:
    all_words: list[str] = []
    for text in texts:
        words = re.findall(r"\b\w+\b", text.lower())
        all_words.extend(words)
    if not all_words:
        return 0.0
    return len(set(all_words)) / len(all_words)


def calculate_signals(
    messages: list[Message],
    *,
    previous_interaction_at: datetime | None = None,
) -> ConversationSignals:
    if not messages:
        return ConversationSignals(
            turns_count=0,
            user_messages_count=0,
            avg_user_msg_length=0.0,
            avg_assistant_msg_length=0.0,
            minutes_since_last_interaction=-1,
            topic_variety=0.0,
            is_technical=False,
            has_humor=False,
            is_long_conversation=False,
            user_seems_tired=False,
            signal_summary="Sin conversación reciente.",
        )

    user_msgs = [m for m in messages if m.role == "user"]
    assistant_msgs = [m for m in messages if m.role == "assistant"]

    avg_user = (
        sum(len(m.content) for m in user_msgs) / len(user_msgs)
        if user_msgs else 0.0
    )
    avg_assistant = (
        sum(len(m.content) for m in assistant_msgs) / len(assistant_msgs)
        if assistant_msgs else 0.0
    )

    minutes_since = -1
    if previous_interaction_at is not None:
        now = datetime.now(timezone.utc)
        prev = previous_interaction_at
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
        delta = now - prev
        minutes_since = max(0, int(delta.total_seconds() / 60))

    all_user_texts = [m.content for m in user_msgs]
    topic_variety = _count_unique_words(all_user_texts)

    joined = "\n".join(m.content for m in messages)
    is_technical = bool(_TECHNICAL_RE.search(joined))
    has_humor = bool(_HUMOR_RE.search(joined))
    is_long = len(messages) >= _LONG_CONVERSATION_TURNS

    very_short = sum(
        1 for m in user_msgs if len(m.content.strip()) < _SHORT_MSG_LEN
    )
    user_seems_tired = (
        bool(_TIRED_RE.search(joined))
        or (len(user_msgs) >= 3 and very_short / max(1, len(user_msgs)) > 0.6)
    )

    parts: list[str] = [
        f"{len(messages)} mensajes ({len(user_msgs)} del usuario, "
        f"{len(assistant_msgs)} de ELI)."
    ]
    if avg_user > 0:
        parts.append(f"Longitud media usuario: {int(avg_user)} caracteres.")
    if minutes_since >= 0:
        parts.append(f"Minutos desde última interacción: {minutes_since}.")
    parts.append(f"Variedad temática: {topic_variety:.2f} (0=poca, 1=mucha).")
    if is_technical:
        parts.append("Conversación técnica (código, infraestructura o tecnología).")
    if has_humor:
        parts.append("Hay señales de humor en la conversación.")
    if is_long:
        parts.append("Conversación larga (más de 20 turnos).")
    if user_seems_tired:
        parts.append("El usuario parece cansado o sus mensajes son muy breves.")

    return ConversationSignals(
        turns_count=len(messages),
        user_messages_count=len(user_msgs),
        avg_user_msg_length=avg_user,
        avg_assistant_msg_length=avg_assistant,
        minutes_since_last_interaction=minutes_since,
        topic_variety=topic_variety,
        is_technical=is_technical,
        has_humor=has_humor,
        is_long_conversation=is_long,
        user_seems_tired=user_seems_tired,
        signal_summary=" ".join(parts),
    )