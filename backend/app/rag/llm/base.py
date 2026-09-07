"""LLM provider abstraction (Section 9/35).

Nothing in `app/agents` or `app/rag` talks to OpenAI/Anthropic/Ollama
SDKs directly — everything goes through this `LLMProvider` Protocol, so the
application isn't coupled to one vendor and can run with zero API keys via
`MockLLMProvider`.

Per Section 35, the LLM is used for reasoning/planning/extraction/
synthesis only — never for arithmetic. Calculations always go through
`app/services/calculations.py`, deterministic Python, regardless of which
provider is configured.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass
class LLMMessage:
    role: Role
    content: str


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: LLMUsage = field(default_factory=LLMUsage)


class LLMProvider(Protocol):
    name: str

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...
