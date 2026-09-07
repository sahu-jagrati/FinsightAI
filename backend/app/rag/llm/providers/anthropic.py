"""Anthropic Messages API provider.

Anthropic's wire protocol separates the system prompt from the message
list and has no native `json_mode` — when `json_mode=True` we append an
explicit instruction instead. Callers must already handle a provider that
doesn't guarantee valid JSON (the mock provider models that too), so this
is consistent with the rest of the abstraction, not a special case.
"""

import httpx

from app.core.config import settings
from app.rag.llm.base import LLMMessage, LLMResponse, LLMUsage

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
_JSON_INSTRUCTION = "\n\nRespond with valid JSON only, and nothing else."


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.LLM_API_KEY
        self.model = model or settings.LLM_MODEL

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        if json_mode:
            system_parts.append(_JSON_INSTRUCTION.strip())
        system_prompt = "\n\n".join(system_parts) or None

        conversation = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]

        payload: dict = {
            "model": self.model,
            "messages": conversation,
            "max_tokens": max_tokens or 2048,
            "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": API_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        content = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

        return LLMResponse(
            content=content,
            model=data.get("model", self.model),
            provider=self.name,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )
