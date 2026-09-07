import httpx
import pytest
import respx

from app.rag.llm.base import LLMMessage
from app.rag.llm.providers.anthropic import AnthropicProvider
from app.rag.llm.providers.mock import MockLLMProvider
from app.rag.llm.providers.openai_compatible import OpenAICompatibleProvider

pytestmark = pytest.mark.asyncio


async def test_mock_provider_json_mode_returns_empty_object():
    provider = MockLLMProvider()
    resp = await provider.chat([LLMMessage("user", "hello")], json_mode=True)
    assert resp.content == "{}"
    assert resp.provider == "mock"


async def test_mock_provider_text_mode_echoes_query():
    provider = MockLLMProvider()
    resp = await provider.chat([LLMMessage("user", "What was Apple's revenue?")])
    assert "Apple's revenue" in resp.content


@respx.mock
async def test_openai_compatible_provider_parses_response():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"content": "Revenue grew 12%."}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )
    )
    provider = OpenAICompatibleProvider(api_key="test-key", model="gpt-4o-mini")

    resp = await provider.chat([LLMMessage("user", "Summarize revenue growth.")])

    assert route.called
    request_body = route.calls[0].request.content
    assert b"Summarize revenue growth" in request_body
    assert resp.content == "Revenue grew 12%."
    assert resp.usage.total_tokens == 15
    assert resp.provider == "openai"


@respx.mock
async def test_openai_compatible_provider_sets_json_response_format():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"model": "gpt-4o-mini", "choices": [{"message": {"content": "{}"}}]},
        )
    )
    provider = OpenAICompatibleProvider(api_key="test-key")
    await provider.chat([LLMMessage("user", "extract entities")], json_mode=True)

    import json

    sent = json.loads(route.calls[0].request.content)
    assert sent["response_format"] == {"type": "json_object"}


@respx.mock
async def test_anthropic_provider_parses_response():
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "claude-opus-5",
                "content": [{"type": "text", "text": "Net income rose."}],
                "usage": {"input_tokens": 8, "output_tokens": 4},
            },
        )
    )
    provider = AnthropicProvider(api_key="test-key", model="claude-opus-5")

    resp = await provider.chat(
        [LLMMessage("system", "You are a financial analyst."), LLMMessage("user", "Summarize.")]
    )

    assert route.called
    import json

    sent = json.loads(route.calls[0].request.content)
    assert sent["system"] == "You are a financial analyst."
    assert sent["messages"] == [{"role": "user", "content": "Summarize."}]
    assert resp.content == "Net income rose."
    assert resp.usage.total_tokens == 12
