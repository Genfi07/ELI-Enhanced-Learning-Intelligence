from app.config.settings import get_settings
from app.core.contracts.llm import LLMProvider
from app.llm.fake_provider import FakeLLMProvider
from app.llm.openai_provider import OpenAIProvider


def build_provider() -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "openai":
        return OpenAIProvider()
    return FakeLLMProvider()


class ModelRouter:
    """Resuelve el modelo a usar según la ruta (FAST/STANDARD/DEEP)."""

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        self._settings = get_settings()

    def model_for(self, route: str) -> str:
        if route == "DEEP":
            return self._settings.llm_deep_model
        return self._settings.llm_default_model