"""Router de LLM: construye la cadena de proveedores.

Comportamiento:
  - Si `llm_provider=fake` → FakeLLMProvider (para tests y dev sin red).
  - Si hay `llm_fallback_chain` definida, construye un FallbackLLMProvider
    con esos providers en orden de prioridad.
  - Si no hay cadena pero hay `openai_api_key`, devuelve un único
    OpenAIProvider (comportamiento anterior).
"""
from __future__ import annotations

from app.config.settings import get_settings
from app.core.contracts.llm import LLMProvider
from app.llm.fake_provider import FakeLLMProvider
from app.llm.fallback_provider import FallbackLLMProvider
from app.llm.openai_provider import OpenAIProvider
from app.observability.logging import get_logger

log = get_logger(__name__)


def _build_provider_for(name: str) -> LLMProvider | None:
    """Construye el provider para un nombre de la cadena de fallback.

    Devuelve None si el proveedor no está configurado (sin API key).
    """
    settings = get_settings()

    if name == "groq":
        if not settings.openai_api_key:
            log.warning("fallback_provider_skipped", name="groq", reason="sin key")
            return None
        return OpenAIProvider(
            name="groq",
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or "https://api.groq.com/openai/v1",
            default_model=settings.llm_default_model,
        )

    if name == "mistral":
        if not settings.mistral_api_key:
            log.warning("fallback_provider_skipped", name="mistral", reason="sin key")
            return None
        return OpenAIProvider(
            name="mistral",
            api_key=settings.mistral_api_key,
            base_url=settings.mistral_base_url,
            default_model=settings.mistral_model,
        )

    if name == "cerebras":
        if not settings.cerebras_api_key:
            log.warning("fallback_provider_skipped", name="cerebras", reason="sin key")
            return None
        return OpenAIProvider(
            name="cerebras",
            api_key=settings.cerebras_api_key,
            base_url=settings.cerebras_base_url,
            default_model=settings.cerebras_model,
        )

    if name == "sambanova":
        if not settings.sambanova_api_key:
            log.warning("fallback_provider_skipped", name="sambanova", reason="sin key")
            return None
        return OpenAIProvider(
            name="sambanova",
            api_key=settings.sambanova_api_key,
            base_url=settings.sambanova_base_url,
            default_model=settings.sambanova_model,
        )

    if name == "openrouter":
        if not settings.openrouter_api_key:
            log.warning("fallback_provider_skipped", name="openrouter", reason="sin key")
            return None
        return OpenAIProvider(
            name="openrouter",
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_model=settings.openrouter_model,
        )

    if name == "gemini":
        if not settings.gemini_api_key:
            log.warning("fallback_provider_skipped", name="gemini", reason="sin key")
            return None
        return OpenAIProvider(
            name="gemini",
            api_key=settings.gemini_api_key,
            base_url=settings.gemini_base_url,
            default_model=settings.gemini_model,
        )

    if name == "ollama":
        # Ollama no necesita key real, pero el SDK de OpenAI exige una no vacía.
        return OpenAIProvider(
            name="ollama",
            api_key="ollama-local",
            base_url=f"{settings.ollama_base_url}/v1",
            default_model=settings.ollama_chat_model,
        )

    log.warning("fallback_provider_unknown", name=name)
    return None


def build_provider() -> LLMProvider:
    settings = get_settings()

    if settings.llm_provider == "fake":
        return FakeLLMProvider()

    chain = [
        name.strip()
        for name in settings.llm_fallback_chain.split(",")
        if name.strip()
    ]

    if chain:
        providers: list[LLMProvider] = []
        for name in chain:
            provider = _build_provider_for(name)
            if provider is not None:
                providers.append(provider)

        if not providers:
            log.warning(
                "fallback_chain_empty",
                chain=settings.llm_fallback_chain,
                hint="ningún proveedor tiene key configurada",
            )
            if settings.openai_api_key:
                return OpenAIProvider()
            raise RuntimeError("no hay ningún proveedor LLM configurado")

        if len(providers) == 1:
            return providers[0]

        log.info(
            "fallback_chain_built",
            chain=[getattr(p, "name", "?") for p in providers],
        )
        return FallbackLLMProvider(providers)

    return OpenAIProvider()


class ModelRouter:
    """Resuelve el modelo a usar según la ruta (FAST/STANDARD/DEEP)."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self._settings = get_settings()

    def model_for(self, route: str) -> str:
        if route == "DEEP":
            return self._settings.llm_deep_model
        return self._settings.llm_default_model