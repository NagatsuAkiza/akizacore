import json
from collections.abc import Callable, Sequence

import httpx
import pytest

from akizacore.ai.providers import (
    ChatMessage,
    LLMResponse,
    OpenAICompatibleProvider,
    ResilientProvider,
    ToolCall,
    ToolSpec,
)
from akizacore.core.exceptions import ProviderUnavailable

MESSAGES = [ChatMessage("user", "halo")]


def provider_with(handler: Callable[[httpx.Request], httpx.Response]) -> OpenAICompatibleProvider:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        name="t", base_url="https://x.test/v1/", api_key="k", model="m", client=client
    )


async def test_chat_parses_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer k"
        assert str(request.url) == "https://x.test/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "model": "m-1",
                "choices": [{"message": {"content": "  halo juga  "}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    result = await provider_with(handler).chat(MESSAGES)
    assert result.content == "halo juga"
    assert result.model == "m-1"
    assert (result.prompt_tokens, result.completion_tokens) == (3, 2)
    assert result.tool_calls == ()


async def test_rate_limit_is_retryable_and_auth_error_is_not() -> None:
    with pytest.raises(ProviderUnavailable) as rate:
        await provider_with(lambda r: httpx.Response(429)).chat(MESSAGES)
    assert rate.value.retryable is True

    with pytest.raises(ProviderUnavailable) as auth:
        await provider_with(lambda r: httpx.Response(401)).chat(MESSAGES)
    assert auth.value.retryable is False


async def test_malformed_response_raises() -> None:
    with pytest.raises(ProviderUnavailable):
        await provider_with(lambda r: httpx.Response(200, json={"oops": 1})).chat(MESSAGES)


async def test_tools_are_sent_and_tool_calls_parsed_with_raw_preserved() -> None:
    seen: dict[str, object] = {}
    raw_call = {
        "id": "abc",
        "type": "function",
        "function": {"name": "get_balance", "arguments": "{}"},
        "extra_content": {"google": {"thought_signature": "SIG"}},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": None, "tool_calls": [raw_call]},
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

    result = await provider_with(handler).chat(
        MESSAGES, tools=[ToolSpec("get_balance", "Lihat saldo")]
    )

    function = seen["tools"][0]["function"]  # type: ignore[index]
    assert function["name"] == "get_balance"
    assert "parameters" not in function  # tool tanpa argumen: parameters dihilangkan

    call = result.tool_calls[0]
    assert (call.id, call.name, call.arguments) == ("abc", "get_balance", "{}")
    assert call.raw["extra_content"] == {"google": {"thought_signature": "SIG"}}
    assert result.finish_reason == "tool_calls"
    assert result.content == ""


async def test_tool_round_trip_serialization() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "selesai"}}]})

    call = ToolCall(
        "abc",
        "get_balance",
        "{}",
        {
            "id": "abc",
            "type": "function",
            "function": {"name": "get_balance", "arguments": "{}"},
            "extra_content": {"google": {"thought_signature": "SIG"}},
        },
    )
    messages = [
        ChatMessage("user", "saldo?"),
        ChatMessage("assistant", "", tool_calls=(call,)),
        ChatMessage("tool", "Saldo 5", tool_call_id="abc"),
    ]
    await provider_with(handler).chat(messages)

    sent = seen["messages"]
    assert sent[1]["content"] is None  # type: ignore[index]
    assert sent[1]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "SIG"}}  # type: ignore[index]
    assert sent[2] == {"role": "tool", "tool_call_id": "abc", "content": "Saldo 5"}  # type: ignore[index]


class Scripted:
    def __init__(self, name: str, results: list[LLMResponse | Exception]) -> None:
        self.name = name
        self.calls = 0
        self.last_tools: Sequence[ToolSpec] | None = None
        self._results = list(results)

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> LLMResponse:
        self.calls += 1
        self.last_tools = tools
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def aclose(self) -> None:
        return None


async def test_chain_retries_then_uses_fallback() -> None:
    primary = Scripted("p", [ProviderUnavailable("down"), ProviderUnavailable("down")])
    fallback = Scripted("f", [LLMResponse("ok", "m")])
    chain = ResilientProvider(primary, fallback, retries=1, backoff_s=0)

    result = await chain.chat(MESSAGES)

    assert result.content == "ok"
    assert (primary.calls, fallback.calls) == (2, 1)


async def test_chain_does_not_retry_non_retryable() -> None:
    primary = Scripted("p", [ProviderUnavailable("bad key", retryable=False)])
    fallback = Scripted("f", [LLMResponse("ok", "m")])
    chain = ResilientProvider(primary, fallback, retries=3, backoff_s=0)

    await chain.chat(MESSAGES)

    assert primary.calls == 1


async def test_chain_passes_tools_through() -> None:
    primary = Scripted("p", [LLMResponse("ok", "m")])
    spec = ToolSpec("t", "d")
    await ResilientProvider(primary, None, retries=0).chat(MESSAGES, tools=[spec])
    assert primary.last_tools == [spec]


async def test_chain_raises_when_everything_fails() -> None:
    primary = Scripted("p", [ProviderUnavailable("x")])
    chain = ResilientProvider(primary, None, retries=0, backoff_s=0)
    with pytest.raises(ProviderUnavailable):
        await chain.chat(MESSAGES)
