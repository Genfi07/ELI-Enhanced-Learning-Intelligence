from app.core.schemas.llm import LLMMessage


def rough_token_count(text: str) -> int:
    """Aproximación razonable (~4 chars/token) para presupuestar contexto.
    Los providers reales pueden reemplazar esto."""
    return max(1, len(text) // 4)


def count_messages_tokens(messages: list[LLMMessage]) -> int:
    # Overhead por mensaje tipo OpenAI chat format ~4 tokens
    return sum(rough_token_count(m.content) + 4 for m in messages)