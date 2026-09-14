"""Tests del MemoryExtractor con LLM mockeado.

Probamos el parsing y los filtros. No probamos la calidad del LLM
(eso es responsabilidad del prompt, no del código).
"""
from __future__ import annotations

import pytest

from app.core.schemas.llm import LLMResponse, TokenUsage
from app.memory.extractor import MemoryExtractor


class StubLLM:
    """LLM controlado que devuelve el texto que le indiquemos."""

    name = "stub"

    def __init__(self, text: str) -> None:
        self.text = text

    async def generate(self, messages, *, model=None, temperature=0.7, max_tokens=None):
        return LLMResponse(
            text=self.text, usage=TokenUsage(), model="stub"
        )

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


def _valid_json() -> str:
    return """{
      "memories": [
        {"type": "FACT", "content": "El usuario trabaja en finanzas",
         "importance": 0.7, "confidence": 0.9},
        {"type": "PREFERENCE", "content": "Prefiere explicaciones paso a paso",
         "importance": 0.9, "confidence": 0.85}
      ]
    }"""


@pytest.mark.asyncio
async def test_extracts_valid_candidates():
    ext = MemoryExtractor(StubLLM(_valid_json()))
    out = await ext.extract("Trabajo en finanzas", "Entendido, anotado.")
    assert len(out) == 2
    assert out[0].type == "FACT"
    assert out[1].type == "PREFERENCE"


@pytest.mark.asyncio
async def test_handles_markdown_fence():
    wrapped = f"```json\n{_valid_json()}\n```"
    ext = MemoryExtractor(StubLLM(wrapped))
    out = await ext.extract("Trabajo en finanzas y quiero aprender", "Muy bien, entonces seguimos con ese plan.")
    assert len(out) == 2


@pytest.mark.asyncio
async def test_handles_text_before_and_after_json():
    wrapped = f"Claro, aquí está:\n{_valid_json()}\nEspero que sirva."
    ext = MemoryExtractor(StubLLM(wrapped))
    out = await ext.extract("Mensaje suficientemente largo como para procesar", "Respuesta también suficientemente larga.")
    assert len(out) == 2


@pytest.mark.asyncio
async def test_ignores_low_confidence():
    raw = """{"memories": [
      {"type": "FACT", "content": "Algo quizás poco fiable",
       "importance": 0.5, "confidence": 0.3}
    ]}"""
    ext = MemoryExtractor(StubLLM(raw))
    out = await ext.extract("Mensaje largo suficiente para no saltar", "Respuesta también larga suficiente.")
    assert out == []


@pytest.mark.asyncio
async def test_ignores_too_short_content():
    raw = """{"memories": [
      {"type": "FACT", "content": "hi", "importance": 0.9, "confidence": 0.9}
    ]}"""
    ext = MemoryExtractor(StubLLM(raw))
    out = await ext.extract("Mensaje largo suficiente para no saltar", "Respuesta también larga suficiente.")
    assert out == []


@pytest.mark.asyncio
async def test_deduplicates_same_content():
    raw = """{"memories": [
      {"type": "FACT", "content": "El usuario trabaja en finanzas",
       "importance": 0.7, "confidence": 0.9},
      {"type": "FACT", "content": "El usuario trabaja en finanzas",
       "importance": 0.6, "confidence": 0.8}
    ]}"""
    ext = MemoryExtractor(StubLLM(raw))
    out = await ext.extract("Mensaje suficientemente largo para procesar", "Respuesta larga.")
    assert len(out) == 1


@pytest.mark.asyncio
async def test_handles_invalid_json():
    ext = MemoryExtractor(StubLLM("esto no es JSON"))
    out = await ext.extract("Mensaje suficientemente largo para procesar", "Respuesta larga.")
    assert out == []


@pytest.mark.asyncio
async def test_handles_llm_exception():
    ext = MemoryExtractor(BrokenLLM())
    out = await ext.extract("Mensaje suficientemente largo para procesar", "Respuesta larga.")
    assert out == []


@pytest.mark.asyncio
async def test_empty_memories():
    ext = MemoryExtractor(StubLLM('{"memories": []}'))
    out = await ext.extract("Mensaje suficientemente largo para procesar", "Respuesta larga.")
    assert out == []


@pytest.mark.asyncio
async def test_skips_very_short_turns():
    ext = MemoryExtractor(StubLLM(_valid_json()))
    # Ambos mensajes muy cortos → ni se llama al LLM
    out = await ext.extract("hola", "hey")
    assert out == []


@pytest.mark.asyncio
async def test_caps_at_max_candidates():
    items = ",".join(
        f'{{"type":"FACT","content":"memoria numero {i}","importance":0.5,"confidence":0.9}}'
        for i in range(10)
    )
    raw = f'{{"memories": [{items}]}}'
    ext = MemoryExtractor(StubLLM(raw))
    out = await ext.extract("Mensaje suficientemente largo para procesar", "Respuesta larga.")
    assert len(out) == 5  # MAX_CANDIDATES