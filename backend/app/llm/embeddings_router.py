"""Selector del proveedor de embeddings con cadena de fallback.

Cadena por defecto ("chain"):
  Gemini → Mistral → Voyage AI → Cohere → Jina → Ollama

Cada proveedor tiene su propia cuota y latencia. El primero que responda
gana. Ollama es el último recurso, siempre disponible localmente.
"""
from app.config.settings import get_settings
from app.core.contracts.embeddings import EmbeddingsProvider
from app.llm.embeddings_cohere import CohereEmbeddingsProvider
from app.llm.embeddings_fake import FakeEmbeddingsProvider
from app.llm.embeddings_fallback import FallbackEmbeddingsProvider
from app.llm.embeddings_gemini import GeminiEmbeddingsProvider
from app.llm.embeddings_jina import JinaEmbeddingsProvider
from app.llm.embeddings_mistral import MistralEmbeddingsProvider
from app.llm.embeddings_ollama import OllamaEmbeddingsProvider
from app.llm.embeddings_openai import OpenAIEmbeddingsProvider
from app.llm.embeddings_voyage import VoyageEmbeddingsProvider
from app.observability.logging import get_logger

log = get_logger(__name__)


def _try_build(provider_name: str, factory) -> EmbeddingsProvider | None:
    try:
        return factory()
    except Exception as exc:
        log.warning(
            "embeddings_provider_init_failed",
            provider=provider_name,
            error=str(exc)[:160],
        )
        return None


def _build_chain() -> EmbeddingsProvider:
    settings = get_settings()
    providers: list[EmbeddingsProvider] = []

    if settings.gemini_api_key:
        p = _try_build("gemini", GeminiEmbeddingsProvider)
        if p is not None:
            providers.append(p)

    if settings.mistral_api_key:
        p = _try_build("mistral-embed", MistralEmbeddingsProvider)
        if p is not None:
            providers.append(p)

    if settings.voyage_api_key:
        p = _try_build("voyage", VoyageEmbeddingsProvider)
        if p is not None:
            providers.append(p)

    if settings.cohere_api_key:
        p = _try_build("cohere", CohereEmbeddingsProvider)
        if p is not None:
            providers.append(p)

    if settings.jina_api_key:
        p = _try_build("jina", JinaEmbeddingsProvider)
        if p is not None:
            providers.append(p)

    p = _try_build("ollama", OllamaEmbeddingsProvider)
    if p is not None:
        providers.append(p)

    if not providers:
        log.warning("embeddings_chain_empty", fallback="fake")
        return FakeEmbeddingsProvider()

    if len(providers) == 1:
        return providers[0]

    log.info(
        "embeddings_chain_built",
        chain=[getattr(p, "name", "?") for p in providers],
    )
    return FallbackEmbeddingsProvider(providers)


def build_embeddings_provider() -> EmbeddingsProvider:
    settings = get_settings()
    if settings.embeddings_provider == "chain":
        return _build_chain()
    if settings.embeddings_provider == "gemini":
        if settings.gemini_api_key:
            p = _try_build("gemini", GeminiEmbeddingsProvider)
            if p is not None:
                return p
        return OllamaEmbeddingsProvider()
    if settings.embeddings_provider == "jina":
        if settings.jina_api_key:
            p = _try_build("jina", JinaEmbeddingsProvider)
            if p is not None:
                return p
        return OllamaEmbeddingsProvider()
    if settings.embeddings_provider == "ollama":
        return OllamaEmbeddingsProvider()
    if settings.embeddings_provider == "openai" and settings.openai_api_key:
        base = (settings.openai_base_url or "").lower()
        if base == "" or "openai.com" in base:
            return OpenAIEmbeddingsProvider()
    return FakeEmbeddingsProvider()