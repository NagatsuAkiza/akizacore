from collections.abc import Callable, Sequence

import httpx
import pytest

from akizacore.ai.providers import (
    ChatMessage,
    LLMResponse,
    OpenAICompatibleProvider,
    ResilientProvider,
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


class Scripted:
    def __init__(self, name: str, results: list[LLMResponse | Exception]) -> None:
        self.name = name
        self.calls = 0
        self._results = list(results)

    async def chat(
        self, messages: Sequence[ChatMessage], *, temperature: float = 0.7, max_tokens: int = 600
    ) -> LLMResponse:
        self.calls += 1
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


async def test_chain_raises_when_everything_fails() -> None:
    primary = Scripted("p", [ProviderUnavailable("x")])
    chain = ResilientProvider(primary, None, retries=0, backoff_s=0)
    with pytest.raises(ProviderUnavailable):
        await chain.chat(MESSAGES)
