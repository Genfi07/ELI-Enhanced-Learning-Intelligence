"""Selector del proveedor de embeddings.

Independiente del proveedor de chat. Casos típicos:
  - Groq chat + fake embeddings (Groq no ofrece embeddings).
  - OpenAI chat + OpenAI embeddings.
  - Ollama chat + Ollama embeddings (nomic-embed-text, padded a 1536).
  - Fake chat + fake embeddings (modo test/dev).
"""
from app.config.settings import get_settings
from app.core.contracts.embeddings import EmbeddingsProvider
from app.llm.embeddings_fake import FakeEmbeddingsProvider
from app.llm.embeddings_ollama import OllamaEmbeddingsProvider
from app.llm.embeddings_openai import OpenAIEmbeddingsProvider


def build_embeddings_provider() -> EmbeddingsProvider:
    settings = get_settings()

    if settings.embeddings_provider == "ollama":
        return OllamaEmbeddingsProvider()

    if settings.embeddings_provider == "openai" and settings.openai_api_key:
        base = (settings.openai_base_url or "").lower()
        if base == "" or "openai.com" in base:
            return OpenAIEmbeddingsProvider()

    return FakeEmbeddingsProvider()