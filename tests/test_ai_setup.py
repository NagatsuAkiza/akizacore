import json

import httpx
import pytest

from akizacore.ai.providers import ChatMessage, OpenAICompatibleProvider
from akizacore.ai.providers.factory import build_fallback, build_primary, parse_extra_body
from akizacore.config.settings import Settings
from akizacore.core.exceptions import ProviderUnavailable

MESSAGES = [ChatMessage("user", "halo")]


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"discord_token": "x"}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


async def test_extra_body_is_sent_but_cannot_override_core_fields() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    provider = OpenAICompatibleProvider(
        name="t",
        base_url="https://x.test/v1",
        api_key="k",
        model="m",
        extra_body={"reasoning_effort": "low", "model": "hack", "max_tokens": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await provider.chat(MESSAGES, max_tokens=500)

    assert seen["reasoning_effort"] == "low"
    assert seen["model"] == "m"
    assert seen["max_tokens"] == 500


async def test_truncated_empty_answer_is_not_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
        )

    provider = OpenAICompatibleProvider(
        name="t",
        base_url="https://x.test/v1",
        api_key="k",
        model="m",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderUnavailable) as error:
        await provider.chat(MESSAGES)
    assert error.value.retryable is False


def test_parse_extra_body() -> None:
    assert parse_extra_body(None, "X") == {}
    assert parse_extra_body("  ", "X") == {}
    assert parse_extra_body('{"reasoning_effort": "low"}', "X") == {"reasoning_effort": "low"}
    with pytest.raises(ValueError):
        parse_extra_body("{bukan json", "X")
    with pytest.raises(ValueError):
        parse_extra_body('["list"]', "X")


def test_builders_return_none_until_fully_configured() -> None:
    assert build_primary(make_settings()) is None
    assert build_fallback(make_settings()) is None

    configured = make_settings(
        ai_base_url="https://x.test/v1",
        ai_api_key="k",
        ai_model_fast="m",
        ai_extra_body='{"reasoning_effort":"low"}',
    )
    assert build_primary(configured) is not None
    assert build_fallback(configured) is None


def test_invalid_extra_body_fails_fast_with_clear_message() -> None:
    bad = make_settings(
        ai_base_url="https://x.test/v1", ai_api_key="k", ai_model_fast="m", ai_extra_body="{oops"
    )
    with pytest.raises(ValueError, match="AI_EXTRA_BODY"):
        build_primary(bad)
