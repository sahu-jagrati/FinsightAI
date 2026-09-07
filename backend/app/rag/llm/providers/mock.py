"""MockLLMProvider — the default provider (`LLM_PROVIDER=mock`), so the
whole application runs with zero external API keys.

It deliberately does NOT try to fake intelligence: for `json_mode` it
returns `{}` (an empty object), and otherwise a short, clearly-labeled
placeholder. Callers must already treat "the LLM returned nothing useful"
as a normal case — deterministic extraction/calculation/retrieval keep
working regardless, and synthesis correctly falls back to "insufficient
evidence" (Section 16) rather than fabricating an answer. Swapping in a
real provider is one env var (`LLM_PROVIDER=openai`, etc.) — no code
change.
"""

from app.rag.llm.base import LLMMessage, LLMResponse, LLMUsage


class MockLLMProvider:
    name = "mock"

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if json_mode:
            content = "{}"
        else:
            last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
            preview = last_user[:120].replace("\n", " ")
            content = (
                "[mock LLM provider — set LLM_PROVIDER to a real provider for actual "
                f"generation] Received: \"{preview}\""
            )

        return LLMResponse(
            content=content,
            model="mock",
            provider=self.name,
            usage=LLMUsage(),
        )
