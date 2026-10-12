from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from akizacore.ai.providers.base import ToolSpec
from akizacore.schemas.discord import UserInfo

_DROP_KEYS = {"title", "default", "additionalProperties"}  # tidak didukung semua provider


def clean_text(value: str, limit: int = 60) -> str:
    """Data buatan user (nama, deskripsi) dirapikan sebelum masuk ke konteks LLM."""
    return " ".join(value.split())[:limit]


def _sanitize(node: object) -> object:
    if isinstance(node, dict):
        return {k: _sanitize(v) for k, v in node.items() if k not in _DROP_KEYS}
    if isinstance(node, list):
        return [_sanitize(v) for v in node]
    return node


@dataclass(frozen=True)
class ToolContext:
    """Identitas peminta. Selalu diisi oleh sistem, tidak pernah dari argumen yang diberikan LLM."""

    server_id: int
    user: UserInfo
    is_admin: bool = False
    features: dict[str, bool] = field(default_factory=dict)
    moderation: "ModerationGateway | None" = None


class ModerationGateway(Protocol):
    """Adapter Discord yang menjaga detail member/role di luar AI layer."""

    async def warn(self, target_id: int, reason: str) -> str: ...

    async def warnings(self, target_id: int) -> str: ...

    async def clear_warnings(self, target_id: int) -> str: ...

    async def modlog(self, target_id: int | None) -> str: ...


ToolHandler = Callable[[ToolContext, Any], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: ToolHandler
    permission: Literal["everyone", "admin"] = "everyone"
    side_effect: Literal["read", "write", "destructive"] = "read"
    feature: str | None = None  # modul yang harus aktif di server
    timeout_s: float = 8.0

    def spec(self) -> ToolSpec:
        schema = self.args_model.model_json_schema()
        if not schema.get("properties"):
            return ToolSpec(self.name, self.description, None)
        cleaned = _sanitize(schema)
        assert isinstance(cleaned, dict)
        return ToolSpec(self.name, self.description, cleaned)
