"""Cek koneksi ke provider AI (utama dan cadangan) tanpa menjalankan bot.

Pakai:
    python scripts/check_ai.py            # tes chat biasa
    python scripts/check_ai.py --tools    # plus tes tool calling (satu putaran penuh)
"""

import asyncio
import sys
import time

from akizacore.ai.providers import ChatMessage, ToolSpec
from akizacore.ai.providers.factory import build_fallback, build_primary
from akizacore.ai.providers.openai_compat import OpenAICompatibleProvider
from akizacore.config import get_settings

PROMPT = "Balas dengan satu kalimat pendek dalam bahasa Indonesia: halo dari AkizaCore."
TOOL_PROMPT = "Panggil tool get_secret_number lalu sebutkan angkanya."
SECRET_TOOL = ToolSpec(
    "get_secret_number", "Mengembalikan angka rahasia. Wajib dipanggil untuk mengetahui angkanya."
)


async def probe_tools(label: str, provider: OpenAICompatibleProvider, max_tokens: int) -> None:
    messages = [ChatMessage("user", TOOL_PROMPT)]
    first = await provider.chat(messages, tools=[SECRET_TOOL], max_tokens=max_tokens)
    if not first.tool_calls:
        print(
            f"[{label}] tool calling: model TIDAK memanggil tool (fitur tool kurang cocok di model ini)"
        )
        return
    call = first.tool_calls[0]
    messages += [
        ChatMessage("assistant", first.content, tool_calls=first.tool_calls),
        ChatMessage("tool", "42", tool_call_id=call.id),
    ]
    second = await provider.chat(messages, max_tokens=max_tokens)
    verdict = "OK" if "42" in second.content else "jalan, tapi jawaban tidak memuat hasil tool"
    print(f"[{label}] tool calling: {verdict}")
    print(f"          jawaban: {second.content[:200]}")


async def probe(
    label: str, provider: OpenAICompatibleProvider | None, max_tokens: int, with_tools: bool
) -> bool:
    if provider is None:
        print(f"[{label}] tidak dikonfigurasi (dilewati)")
        return False
    started = time.perf_counter()
    try:
        result = await provider.chat([ChatMessage("user", PROMPT)], max_tokens=max_tokens)
        elapsed = time.perf_counter() - started
        print(
            f"[{label}] OK  model={result.model}  {elapsed:.1f}s  "
            f"token masuk/keluar={result.prompt_tokens}/{result.completion_tokens}"
        )
        print(f"          jawaban: {result.content[:200]}")
        if with_tools:
            await probe_tools(label, provider, max_tokens)
        return True
    except Exception as exc:
        detail = getattr(exc, "detail", None) or exc
        print(f"[{label}] GAGAL: {detail}")
        return False
    finally:
        await provider.aclose()


async def main() -> int:
    settings = get_settings()
    max_tokens = settings.ai_max_output_tokens
    with_tools = "--tools" in sys.argv
    primary_ok = await probe("utama", build_primary(settings), max_tokens, with_tools)
    await probe("cadangan", build_fallback(settings), max_tokens, with_tools)
    return 0 if primary_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
