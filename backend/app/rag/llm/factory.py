from functools import lru_cache

from app.core.config import settings
from app.rag.llm.base import LLMProvider
from app.rag.llm.providers.anthropic import AnthropicProvider
from app.rag.llm.providers.mock import MockLLMProvider
from app.rag.llm.providers.openai_compatible import OpenAICompatibleProvider

_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


@lru_cache
def get_llm_provider() -> LLMProvider:
    match settings.LLM_PROVIDER:
        case "openai":
            return OpenAICompatibleProvider()
        case "anthropic":
            return AnthropicProvider()
        case "ollama":
            # Ollama's OpenAI-compatibility layer speaks the same protocol;
            # it just doesn't require a real API key.
            return OpenAICompatibleProvider(
                api_key=settings.LLM_API_KEY or "ollama",
                base_url=settings.LLM_BASE_URL or _OLLAMA_DEFAULT_BASE_URL,
            )
        case _:
            return MockLLMProvider()
