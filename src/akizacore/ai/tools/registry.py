from collections.abc import Iterable

from akizacore.ai.providers.base import ToolSpec
from akizacore.ai.tools.base import Tool, ToolContext


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool sudah terdaftar: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def unavailable_reason(self, tool: Tool, ctx: ToolContext) -> str | None:
        """None bila tool boleh dipakai user ini di server ini."""
        if tool.feature is not None and not ctx.features.get(tool.feature, False):
            return f"Ditolak: modul {tool.feature} dimatikan di server ini."
        if tool.permission == "admin" and not ctx.is_admin:
            return "Ditolak: tool ini butuh izin Manage Server."
        return None

    def specs_for(self, ctx: ToolContext) -> list[ToolSpec]:
        """Tool yang ditawarkan ke LLM. Aksi destruktif tetap harus melalui konfirmasi."""
        return [
            tool.spec()
            for tool in self._tools.values()
            if tool.side_effect != "destructive" and self.unavailable_reason(tool, ctx) is None
        ]
