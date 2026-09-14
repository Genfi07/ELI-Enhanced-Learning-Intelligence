"""Tests del ConversationSummarizer (funciones puras + LLM stub).

Verifican:
  - should_summarize: umbral correcto.
  - slice_to_summarize: idempotencia y preservación de recientes.
  - summarize: llamada al LLM, manejo de errores, cadena vacía.
"""
from __future__ import annotations

import pytest

from app.core.schemas.llm import LLMResponse, TokenUsage
from app.memory.summarizer import ConversationSummarizer


class StubLLM:
    name = "stub"

    def __init__(self, text: str = "Resumen generado.") -> None:
        self.text = text
        self.calls = 0

    async def generate(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        self.calls += 1
        return LLMResponse(text=self.text, usage=TokenUsage(), model="stub")

    async def stream(self, *args, **kwargs):  # pragma: no cover
        yield None

    def count_tokens(self, messages) -> int:
        return 0


class BrokenLLM:
    name = "broken"

    async def generate(self, *args, **kwargs):
        raise RuntimeError("boom")

    async def stream(self, *args, **kwargs):  # pragma: no cover
        yield None

    def count_tokens(self, messages) -> int:
        return 0


# --------------------------------------------------------------------------- #
# should_summarize
# --------------------------------------------------------------------------- #
def test_should_summarize_below_threshold():
    s = ConversationSummarizer(StubLLM())
    assert s.should_summarize(total_messages=10, summarized_count=0, threshold=40) is False


def test_should_summarize_exactly_at_threshold():
    s = ConversationSummarizer(StubLLM())
    assert s.should_summarize(total_messages=40, summarized_count=0, threshold=40) is True


def test_should_summarize_accounts_for_already_summarized():
    s = ConversationSummarizer(StubLLM())
    # 50 total, 30 ya resumidos → 20 sin resumir < 40
    assert s.should_summarize(total_messages=50, summarized_count=30, threshold=40) is False


# --------------------------------------------------------------------------- #
# slice_to_summarize
# --------------------------------------------------------------------------- #
def test_slice_preserves_recent():
    s = ConversationSummarizer(StubLLM(), keep_recent=3)
    msgs = [(f"r{i}", f"m{i}") for i in range(10)]
    # total=10, keep=3 → cutoff=7, slice=[0:7]
    out = s.slice_to_summarize(msgs, summarized_count=0)
    assert len(out) == 7
    assert out[0][1] == "m0"
    assert out[-1][1] == "m6"


def test_slice_respects_summarized_count():
    s = ConversationSummarizer(StubLLM(), keep_recent=3)
    msgs = [(f"r{i}", f"m{i}") for i in range(10)]
    # Ya resumidos hasta 4 → slice=[4:7]
    out = s.slice_to_summarize(msgs, summarized_count=4)
    assert len(out) == 3
    assert out[0][1] == "m4"
    assert out[-1][1] == "m6"


def test_slice_empty_when_everything_is_recent():
    s = ConversationSummarizer(StubLLM(), keep_recent=5)
    msgs = [(f"r{i}", f"m{i}") for i in range(5)]
    # total=5, keep=5 → cutoff=5, slice=[0:5] con summarized_count=0 → nada
    out = s.slice_to_summarize(msgs, summarized_count=0)
    # cutoff = max(0, 5-5) = 0 → vacío
    assert out == []


def test_slice_idempotent_after_full_pass():
    """Tras resumir todo, no debe quedar nada por resumir."""
    s = ConversationSummarizer(StubLLM(), keep_recent=3)
    msgs = [(f"r{i}", f"m{i}") for i in range(10)]
    out1 = s.slice_to_summarize(msgs, summarized_count=0)
    new_count = 0 + len(out1)  # 7
    out2 = s.slice_to_summarize(msgs, summarized_count=new_count)
    assert out2 == []


# --------------------------------------------------------------------------- #
# summarize
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_summarize_returns_llm_text():
    s = ConversationSummarizer(StubLLM("Resumen: usuario pidió X."))
    out = await s.summarize([("user", "quiero X"), ("assistant", "aquí va X")])
    assert out == "Resumen: usuario pidió X."


@pytest.mark.asyncio
async def test_summarize_empty_input_returns_empty():
    s = ConversationSummarizer(StubLLM())
    out = await s.summarize([])
    assert out == ""


@pytest.mark.asyncio
async def test_summarize_llm_exception_returns_empty():
    s = ConversationSummarizer(BrokenLLM())
    out = await s.summarize([("user", "hola"), ("assistant", "hey")])
    assert out == ""


@pytest.mark.asyncio
async def test_summarize_strips_whitespace():
    s = ConversationSummarizer(StubLLM("  con espacios  \n"))
    out = await s.summarize([("user", "x"), ("assistant", "y")])
    assert out == "con espacios"