from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMProvider(Protocol):
    """Satu interface untuk semua provider (Groq, Gemini, OpenRouter, ...)."""

    name: str

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...
