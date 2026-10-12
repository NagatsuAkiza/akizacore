"""Cek koneksi ke provider AI (utama dan cadangan) tanpa menjalankan bot.

Pakai:  python scripts/check_ai.py
"""

import asyncio
import sys
import time

from akizacore.ai.providers import ChatMessage
from akizacore.ai.providers.factory import build_fallback, build_primary
from akizacore.ai.providers.openai_compat import OpenAICompatibleProvider
from akizacore.config import get_settings

PROMPT = "Balas dengan satu kalimat pendek dalam bahasa Indonesia: halo dari AkizaCore."


async def probe(label: str, provider: OpenAICompatibleProvider | None, max_tokens: int) -> bool:
    if provider is None:
        print(f"[{label}] tidak dikonfigurasi (dilewati)")
        return False
    started = time.perf_counter()
    try:
        result = await provider.chat([ChatMessage("user", PROMPT)], max_tokens=max_tokens)
    except Exception as exc:
        detail = getattr(exc, "detail", None) or exc
        print(f"[{label}] GAGAL: {detail}")
        return False
    finally:
        await provider.aclose()
    elapsed = time.perf_counter() - started
    print(
        f"[{label}] OK  model={result.model}  {elapsed:.1f}s  "
        f"token masuk/keluar={result.prompt_tokens}/{result.completion_tokens}"
    )
    print(f"          jawaban: {result.content[:200]}")
    return True


async def main() -> int:
    settings = get_settings()
    max_tokens = settings.ai_max_output_tokens
    primary_ok = await probe("utama", build_primary(settings), max_tokens)
    await probe("cadangan", build_fallback(settings), max_tokens)
    return 0 if primary_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
