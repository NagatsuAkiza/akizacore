import asyncio
from collections.abc import Sequence

import structlog

from akizacore.ai.providers.base import ChatMessage, LLMProvider, LLMResponse
from akizacore.core.exceptions import ProviderUnavailable

log = structlog.get_logger()


class ResilientProvider:
    """Retry di provider utama, lalu jatuh ke provider cadangan bila tetap gagal."""

    name = "resilient"

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None = None,
        *,
        retries: int = 1,
        backoff_s: float = 1.0,
    ) -> None:
        self._providers = [p for p in (primary, fallback) if p is not None]
        self._attempts = retries + 1
        self._backoff_s = backoff_s

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 600,
    ) -> LLMResponse:
        last_error: ProviderUnavailable | None = None
        for provider in self._providers:
            for attempt in range(self._attempts):
                try:
                    return await provider.chat(
                        messages, temperature=temperature, max_tokens=max_tokens
                    )
                except ProviderUnavailable as exc:
                    last_error = exc
                    log.warning(
                        "provider_failed",
                        provider=provider.name,
                        attempt=attempt + 1,
                        detail=exc.detail,
                    )
                    if not exc.retryable:
                        break
                    if attempt < self._attempts - 1:
                        await asyncio.sleep(self._backoff_s)
        raise last_error or ProviderUnavailable("tidak ada provider terkonfigurasi")

    async def aclose(self) -> None:
        for provider in self._providers:
            await provider.aclose()
