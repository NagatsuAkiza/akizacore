from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, Self

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Definisi tool yang ditawarkan ke model (JSON schema parameter, None bila tanpa argumen)."""

    name: str
    description: str
    parameters: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Permintaan pemanggilan tool dari model.

    `raw` menyimpan objek tool_call asli dari provider dan dikirim balik apa adanya
    (penting: Gemini 3 membutuhkan field seperti thought_signature di dalamnya).
    """

    id: str
    name: str
    arguments: str = "{}"
    raw: dict[str, object] = field(default_factory=dict)

    @classmethod
    def create(cls, call_id: str, name: str, arguments: str = "{}") -> Self:
        raw: dict[str, object] = {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        }
        return cls(call_id, name, arguments, raw)


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = None


class LLMProvider(Protocol):
    """Satu interface untuk semua provider (Groq, Gemini, OpenRouter, ...)."""

    name: str

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...
