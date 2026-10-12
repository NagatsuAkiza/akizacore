from collections.abc import Sequence

from akizacore.ai.providers import ChatMessage, LLMResponse, ToolSpec
from akizacore.core.exceptions import ProviderUnavailable


class FakeLLM:
    """LLM palsu untuk test.

    - `script`: daftar LLMResponse yang dikembalikan berurutan (mis. untuk simulasi tool call).
      Setelah habis, kembali menjawab `reply`.
    - `calls` mencatat pesan tiap panggilan, `tool_offers` mencatat tool yang ditawarkan.
    """

    name = "fake"

    def __init__(
        self,
        reply: str = "jawaban",
        fail: bool = False,
        script: list[LLMResponse] | None = None,
    ) -> None:
        self.reply = reply
        self.fail = fail
        self._script = list(script or [])
        self.calls: list[list[ChatMessage]] = []
        self.tool_offers: list[list[ToolSpec] | None] = []

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        self.tool_offers.append(list(tools) if tools else None)
        if self.fail:
            raise ProviderUnavailable("fake down")
        if self._script:
            return self._script.pop(0)
        return LLMResponse(
            content=self.reply, model="fake-model", prompt_tokens=10, completion_tokens=5
        )

    async def aclose(self) -> None:
        return None
