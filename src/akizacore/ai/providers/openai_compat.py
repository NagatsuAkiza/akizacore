import json
import uuid
from collections.abc import Sequence
from typing import Any

import httpx

from akizacore.ai.providers.base import ChatMessage, LLMResponse, ToolCall, ToolSpec
from akizacore.core.exceptions import ProviderUnavailable

_RETRYABLE_STATUS = {408, 409, 425, 429}


def _default_raw(call: ToolCall) -> dict[str, object]:
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": call.name, "arguments": call.arguments},
    }


def _serialize(message: ChatMessage) -> dict[str, object]:
    if message.role == "tool":
        # sengaja tanpa field "name": Groq menolak messages[].name
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    data: dict[str, object] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        data["content"] = message.content or None
        data["tool_calls"] = [call.raw or _default_raw(call) for call in message.tool_calls]
    return data


def _tool_definition(spec: ToolSpec) -> dict[str, object]:
    function: dict[str, object] = {"name": spec.name, "description": spec.description}
    if spec.parameters:
        function["parameters"] = spec.parameters
    return {"type": "function", "function": function}


def _parse_tool_calls(raw_calls: Any) -> tuple[ToolCall, ...]:
    if not raw_calls:
        return ()
    calls: list[ToolCall] = []
    for raw in raw_calls:
        function = raw["function"]
        arguments = function.get("arguments")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments or {})
        call_id = str(raw.get("id") or f"call_{uuid.uuid4().hex[:12]}")
        stored: dict[str, object] = dict(raw)
        stored["id"] = call_id
        stored.setdefault("type", "function")
        calls.append(ToolCall(call_id, str(function["name"]), arguments or "{}", stored))
    return tuple(calls)


class OpenAICompatibleProvider:
    """Klien untuk endpoint `/chat/completions` format OpenAI.

    `extra_body` dipakai untuk parameter khusus provider (mis. `reasoning_effort`).
    Field inti (model, messages, tools, temperature, max_tokens) tidak bisa ditimpa lewat extra_body.
    """

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        extra_body: dict[str, object] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._extra_body = dict(extra_body or {})
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> LLMResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [_serialize(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [_tool_definition(t) for t in tools]
        for key, value in self._extra_body.items():
            payload.setdefault(key, value)

        try:
            response = await self._client.post(
                self._url, json=payload, headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{self.name}: {type(exc).__name__}") from exc

        if response.status_code != 200:
            retryable = response.status_code in _RETRYABLE_STATUS or response.status_code >= 500
            raise ProviderUnavailable(
                f"{self.name}: HTTP {response.status_code}", retryable=retryable
            )

        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            content = message.get("content")
            tool_calls = _parse_tool_calls(message.get("tool_calls"))
            finish_reason = choice.get("finish_reason")
            usage = data.get("usage") or {}
            model = str(data.get("model") or self._model)
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderUnavailable(f"{self.name}: respons tidak valid", retryable=False) from exc

        text = content.strip() if isinstance(content, str) else ""
        if not text and not tool_calls:
            # Model reasoning bisa menghabiskan seluruh batas token untuk "berpikir":
            # mengulang request yang sama tidak akan membantu, jadi jangan di-retry.
            truncated = finish_reason == "length"
            raise ProviderUnavailable(
                f"{self.name}: respons kosong (finish_reason={finish_reason}); "
                "naikkan AI_MAX_OUTPUT_TOKENS atau turunkan reasoning_effort",
                retryable=not truncated,
            )
        return LLMResponse(
            content=text,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tool_calls=tool_calls,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
