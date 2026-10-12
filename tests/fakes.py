from collections.abc import Sequence

from akizacore.ai.providers import ChatMessage, LLMResponse
from akizacore.core.exceptions import ProviderUnavailable


class FakeLLM:
    """LLM palsu untuk test: mencatat semua pesan yang diterima."""

    name = "fake"

    def __init__(self, reply: str = "jawaban", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.calls: list[list[ChatMessage]] = []

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        if self.fail:
            raise ProviderUnavailable("fake down")
        return LLMResponse(
            content=self.reply, model="fake-model", prompt_tokens=10, completion_tokens=5
        )

    async def aclose(self) -> None:
        return None
