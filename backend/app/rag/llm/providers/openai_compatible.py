"""OpenAI-compatible chat completions provider.

Works with OpenAI itself and anything speaking the same wire protocol —
Groq, Together, Fireworks, a local vLLM/Ollama OpenAI-compat server, etc.
— by pointing `LLM_BASE_URL` at it. Nothing here is OpenAI-specific beyond
the request/response shape, which is why it's named for the protocol, not
the vendor.
"""

import httpx

from app.core.config import settings
from app.rag.llm.base import LLMMessage, LLMResponse, LLMUsage

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.LLM_API_KEY
        self.base_url = (base_url or settings.LLM_BASE_URL or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage") or {}

        return LLMResponse(
            content=choice,
            model=data.get("model", self.model),
            provider=self.name,
            usage=LLMUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
        )
