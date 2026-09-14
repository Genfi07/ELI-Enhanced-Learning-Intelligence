from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ELI_", extra="ignore")

    # App
    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://eli:eli@localhost:5432/eli"
    )

    # LLM
    llm_provider: Literal["openai", "fake"] = "fake"
    llm_default_model: str = "gpt-4o-mini"
    llm_deep_model: str = "gpt-4o"
    llm_request_timeout_s: int = 120
    openai_api_key: str | None = None
    # base_url del endpoint OpenAI-compatible:
    #   OpenAI:   (vacío) o "https://api.openai.com/v1"
    #   DeepSeek: "https://api.deepseek.com"
    #   Ollama:   "http://localhost:11434/v1"
    openai_base_url: str | None = None

    # Embeddings (independiente del chat)
    #   "openai" → OpenAI real
    #   "ollama" → Ollama local (nomic-embed-text, padded a 1536)
    #   "fake"   → hash determinista (dev/test)
    embeddings_provider: Literal["openai", "ollama", "fake"] = "fake"
    ollama_base_url: str = "http://localhost:11434"
    ollama_embeddings_model: str = "nomic-embed-text"

    # Context / budgets (v1)
    max_context_tokens: int = 16_000
    max_response_tokens: int = 1_024
    max_tool_calls: int = 4
    history_recent_messages: int = 20

    # Observability
    trace_enabled: bool = True

    # Cookies / sesión (Fase 2)
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cookie_domain: str | None = None
    session_ttl_days: int = 30

    # Google OAuth (Fase 2)
    secret_key: str = "cambia-esto-en-produccion-con-algo-seguro"
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    oauth_redirect_after_login: str = "/"

    # Memory (Fase 3)
    memory_enabled: bool = True
    memory_extraction_enabled: bool = True
    memory_top_k: int = 5
    memory_token_budget: int = 600

    # Reasoning & Planning (Fase 4)
    planning_enabled: bool = True
    planning_max_steps: int = 6
    planning_step_max_tokens: int = 800
    planning_final_context_chars: int = 8_000

    # Summarization (Fase 4)
    summarization_enabled: bool = True
    summarization_threshold: int = 40
    summarization_keep_recent: int = 20

    # RAG / Storage (Fase 5)
    storage_root: str = "/tmp/eli-storage"
    max_upload_size_mb: int = 25
    rag_enabled: bool = True
    rag_top_k: int = 6
    rag_token_budget: int = 1_500
    rag_max_chunks_per_doc: int = 500
    ingestion_enabled: bool = True

    # Tools (Fase 6)
    tavily_api_key: str | None = None
    web_fetch_max_bytes: int = 500_000
    web_fetch_timeout_s: int = 15
    tools_max_result_chars: int = 8_000


@lru_cache
def get_settings() -> Settings:
    return Settings()