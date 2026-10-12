import asyncio

import structlog
from pydantic import ValidationError

from akizacore.ai.providers.base import ToolCall
from akizacore.ai.tools.base import ToolContext
from akizacore.ai.tools.registry import ToolRegistry
from akizacore.core.exceptions import AkizaError

log = structlog.get_logger()

MAX_RESULT_CHARS = 1500


def _short(exc: ValidationError) -> str:
    parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
    return "; ".join(parts)[:200]


class ToolExecutor:
    """Menjalankan tool dengan urutan pengecekan: ada? -> boleh? -> aman? -> argumen -> timeout.

    Hasil selalu berupa teks (error pun dikembalikan sebagai teks agar LLM bisa menjelaskannya).
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(self, call: ToolCall, ctx: ToolContext) -> str:
        return await self.run_named(call.name, call.arguments, ctx)

    async def run_named(self, name: str, raw_args: str, ctx: ToolContext) -> str:
        tool = self._registry.get(name)
        if tool is None:
            return f"Error: tool '{name}' tidak dikenal."
        reason = self._registry.unavailable_reason(tool, ctx)
        if reason is not None:
            log.info("tool_denied", tool=name, user_id=ctx.user.id, server_id=ctx.server_id)
            return reason
        if tool.side_effect == "destructive":
            return (
                "Ditahan: aksi ini butuh konfirmasi pengguna dan belum bisa dijalankan lewat chat."
            )
        try:
            args = tool.args_model.model_validate_json(raw_args or "{}")
        except ValidationError as exc:
            return f"Error: argumen tidak valid ({_short(exc)})."

        try:
            result = await asyncio.wait_for(tool.handler(ctx, args), timeout=tool.timeout_s)
        except TimeoutError:
            log.warning("tool_timeout", tool=name, server_id=ctx.server_id)
            return "Error: tool timeout."
        except AkizaError as exc:
            return f"Error: {exc.user_message}"
        except Exception:
            log.exception("tool_failed", tool=name, server_id=ctx.server_id)
            return "Error: tool gagal dijalankan."
        log.info("tool_executed", tool=name, user_id=ctx.user.id, server_id=ctx.server_id)
        return result[:MAX_RESULT_CHARS]
