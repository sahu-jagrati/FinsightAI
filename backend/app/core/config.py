"""Centralized application configuration.

All runtime configuration is read from environment variables (see
`.env.example` at the repo root). Nothing here should ever contain a real
secret — defaults exist only to make local development work out of the box.

Later phases (RAG, agents, caching) add settings here rather than scattering
`os.getenv()` calls through the codebase, so this file grows over the
project's lifetime but stays the single source of truth for configuration.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolved from this file's own location so env-file loading works no
# matter what the process's current working directory is (native `uvicorn`/
# `alembic` run from backend/, `python -c ...` run from the repo root,
# pytest run from either) — a CWD-relative path like "../.env" only works
# from one specific launch directory and silently breaks from any other.
_BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/app/core -> backend/
_REPO_ROOT = _BACKEND_DIR.parent

# Config architecture: the repo-root `.env` (see `.env.example`) is the one
# file `docker-compose.yml` and native runs are both meant to share. An
# optional `backend/.env` can override individual values for a native-only
# tweak (e.g. pointing at a differently-mapped Postgres port) without
# touching the shared file — pydantic-settings loads these in order and
# later files win; a missing file is silently skipped either way. Real
# process environment variables (what Docker Compose actually injects into
# containers via its own `environment:`/`env_file:` handling) always take
# priority over both, so this list only matters for native runs.
_ENV_FILES = (_REPO_ROOT / ".env", _BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General -------------------------------------------------------
    APP_NAME: str = "FinSight AI"
    ENV: Literal["local", "development", "staging", "production", "test"] = "local"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api"
    SECRET_KEY: str = "change-me-in-production"

    # --- CORS ------------------------------------------------------------
    # Deliberately a plain `str`, not `list[str]`: pydantic-settings tries to
    # JSON-decode env values for any list/dict/set field before a
    # field_validator ever runs, so a comma-separated value like
    # "http://localhost:3000,http://127.0.0.1:3000" (valid shell/.env syntax,
    # invalid JSON) raises a hard `SettingsError` at import time no matter
    # what the validator would have done with it. Keeping the field a plain
    # string and splitting it in the `cors_origins` property below sidesteps
    # that source-level JSON decoding entirely.
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Database ----------------------------------------------------------
    # Async URL used by the running application (asyncpg driver).
    DATABASE_URL: str = (
        "postgresql+asyncpg://finsight:finsight@localhost:5432/finsight"
    )
    # Sync URL used by Alembic migrations (psycopg driver via asyncpg is not
    # supported by Alembic's default runner, so we keep a plain psycopg URL).
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg://finsight:finsight@localhost:5432/finsight"
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_ECHO: bool = False

    # --- Redis ---------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL_SECONDS: int = 3600
    REDIS_RATE_LIMIT_PER_MINUTE: int = 60

    # --- File uploads ----------------------------------------------------
    MAX_UPLOAD_MB: int = 50
    # Plain `str` for the same reason as BACKEND_CORS_ORIGINS above — see
    # `allowed_upload_extensions` below for the parsed list.
    ALLOWED_UPLOAD_EXTENSIONS: str = ".pdf,.txt,.html,.md"
    UPLOAD_DIR: str = "./data/uploads"

    # --- LLM provider abstraction (see app/rag/llm) -----------------------
    # Provider-agnostic: any OpenAI-compatible endpoint (OpenAI, Groq,
    # Together, vLLM, Ollama's OpenAI-compat server, etc.) or Anthropic.
    LLM_PROVIDER: Literal["openai", "anthropic", "ollama", "mock"] = "mock"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str | None = None
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.1
    LLM_REQUEST_TIMEOUT_SECONDS: int = 60

    # --- Embeddings (Hugging Face) ---------------------------------------
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSIONS: int = 384
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_BATCH_SIZE: int = 32

    # --- Retrieval ---------------------------------------------------------
    HYBRID_SEARCH_ALPHA: float = 0.6  # weight on dense score, [0,1]
    RETRIEVAL_TOP_K: int = 8
    RERANK_TOP_N: int = 5
    RERANKER_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_ENABLED: bool = True

    # --- Ingestion / chunking ---------------------------------------------
    CHUNK_SIZE_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 64

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_upload_extensions(self) -> list[str]:
        return [e.strip() for e in self.ALLOWED_UPLOAD_EXTENSIONS.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
