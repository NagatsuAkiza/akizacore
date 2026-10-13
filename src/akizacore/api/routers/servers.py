import math
from datetime import datetime
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Query
from pydantic import BaseModel, field_validator

from akizacore.api.deps import (
    CurrentSessionDep,
    HttpClientDep,
    ManagedServerDep,
    ServicesDep,
    SettingsDep,
    fetch_user_guilds,
    has_manage_permission,
)
from akizacore.schemas.settings import SettingsUpdate

log = structlog.get_logger()
router = APIRouter(prefix="/servers", tags=["servers"])


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int


class ServerStatsResponse(BaseModel):
    member_count: int
    total_messages: int
    ai_queries_today: int
    economy_transactions_today: int
    active_warnings: int
    mod_actions_today: int
    economy_accounts: int
    coins_in_circulation: int
    ai_requests_today: int
    ai_requests_7d: int


class LeaderboardEntryResponse(BaseModel):
    user_id: str
    username: str
    balance: int
    level: int
    xp: int
    rank: int


class ModLogEntryResponse(BaseModel):
    id: int
    action: str
    moderator_id: str
    moderator_name: str
    target_id: str
    target_name: str
    reason: str | None = None
    created_at: datetime


class WarningResponse(BaseModel):
    id: int
    user_id: str
    username: str
    moderator_id: str
    moderator_name: str
    reason: str
    created_at: datetime


class ServerResponse(BaseModel):
    id: str
    name: str
    icon: str | None = None
    owner: bool = False
    bot_active: bool = False


class ServerSettingsResponse(BaseModel):
    server_id: str
    prefix: str
    log_channel_id: str | None = None
    welcome_channel_id: str | None = None
    autorole_id: str | None = None
    ai_persona: str | None = None
    welcome_message: str | None = None
    features: dict[str, bool]


class ServerSettingsUpdateRequest(BaseModel):
    prefix: str | None = None
    log_channel_id: int | str | None = None
    welcome_channel_id: int | str | None = None
    autorole_id: int | str | None = None
    ai_persona: str | None = None
    welcome_message: str | None = None
    features: dict[str, bool] | None = None

    @field_validator("log_channel_id", "welcome_channel_id", "autorole_id", mode="before")
    @classmethod
    def _parse_channel_id(cls, v: Any) -> int | None:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            raise ValueError("ID channel/role harus berupa angka.") from None

    @field_validator("prefix")
    @classmethod
    def _validate_prefix(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not 1 <= len(value) <= 5 or any(char.isspace() for char in value):
            raise ValueError("Prefix harus terdiri dari 1 sampai 5 karakter tanpa spasi.")
        if value.startswith("<@"):
            raise ValueError("Prefix tidak boleh berupa mention Discord.")
        return value


@router.get("", summary="Daftar server yang dikelola user", response_model=list[ServerResponse])
async def list_servers(
    session: CurrentSessionDep,
    services: ServicesDep,
    settings: SettingsDep,
    http_client: HttpClientDep,
) -> list[ServerResponse]:
    guilds = await fetch_user_guilds(
        session=session,
        services=services,
        http_client=http_client,
        cache_ttl_s=settings.guild_cache_ttl_s,
    )
    manageable = [g for g in guilds if has_manage_permission(g)]
    if not manageable:
        return []

    guild_ids: list[int] = []
    for g in manageable:
        try:
            guild_ids.append(int(g["id"]))
        except (ValueError, TypeError):
            continue

    active_ids = await services.onboarding.get_active_server_ids(guild_ids)

    return [
        ServerResponse(
            id=str(g["id"]),
            name=str(g.get("name", "")),
            icon=g.get("icon"),
            owner=bool(g.get("owner", False)),
            bot_active=int(g["id"]) in active_ids,
        )
        for g in manageable
    ]


@router.get(
    "/{server_id}",
    summary="Detail server yang dikelola",
    response_model=ServerResponse,
)
async def get_server_detail(ctx: ManagedServerDep) -> ServerResponse:
    return ServerResponse(
        id=str(ctx.server.id),
        name=ctx.server.name,
        icon=ctx.guild.get("icon"),
        owner=bool(ctx.guild.get("owner", False)),
        bot_active=ctx.server.is_active,
    )


@router.get(
    "/{server_id}/settings",
    summary="Ambil konfigurasi server",
    response_model=ServerSettingsResponse,
)
async def get_server_settings(
    ctx: ManagedServerDep,
    services: ServicesDep,
) -> ServerSettingsResponse:
    settings = await services.settings.get(ctx.id)
    return ServerSettingsResponse(
        server_id=str(settings.server_id),
        prefix=settings.prefix,
        log_channel_id=str(settings.log_channel_id)
        if settings.log_channel_id is not None
        else None,
        welcome_channel_id=(
            str(settings.welcome_channel_id) if settings.welcome_channel_id is not None else None
        ),
        autorole_id=str(settings.autorole_id) if settings.autorole_id is not None else None,
        ai_persona=settings.ai_persona,
        welcome_message=None,
        features=settings.features,
    )


@router.put(
    "/{server_id}/settings",
    summary="Perbarui konfigurasi server",
    response_model=ServerSettingsResponse,
)
async def update_server_settings(
    ctx: ManagedServerDep,
    body: ServerSettingsUpdateRequest,
    services: ServicesDep,
) -> ServerSettingsResponse:
    clean_kwargs: dict[str, Any] = {}
    if body.model_fields_set:
        for field in (
            "log_channel_id",
            "welcome_channel_id",
            "autorole_id",
            "ai_persona",
            "prefix",
            "features",
        ):
            if field in body.model_fields_set:
                clean_kwargs[field] = getattr(body, field)

    update_payload = SettingsUpdate(**clean_kwargs)
    updated = await services.settings.update(ctx.id, update_payload)

    return ServerSettingsResponse(
        server_id=str(updated.server_id),
        prefix=updated.prefix,
        log_channel_id=str(updated.log_channel_id) if updated.log_channel_id is not None else None,
        welcome_channel_id=(
            str(updated.welcome_channel_id) if updated.welcome_channel_id is not None else None
        ),
        autorole_id=str(updated.autorole_id) if updated.autorole_id is not None else None,
        ai_persona=updated.ai_persona,
        welcome_message=None,
        features=updated.features,
    )


@router.get(
    "/{server_id}/stats",
    summary="Statistik ringkas server",
    response_model=ServerStatsResponse,
)
async def get_server_stats(
    ctx: ManagedServerDep,
    services: ServicesDep,
) -> ServerStatsResponse:
    stats = await services.stats.snapshot(ctx.id)
    return ServerStatsResponse(
        member_count=stats.member_count,
        total_messages=stats.total_messages,
        ai_queries_today=stats.ai_queries_today,
        economy_transactions_today=stats.economy_transactions_today,
        active_warnings=stats.active_warnings,
        mod_actions_today=stats.mod_actions_today,
        economy_accounts=stats.economy_accounts,
        coins_in_circulation=stats.coins_in_circulation,
        ai_requests_today=stats.ai_requests_today,
        ai_requests_7d=stats.ai_requests_7d,
    )


@router.get(
    "/{server_id}/economy/leaderboard",
    summary="Leaderboard ekonomi server",
    response_model=PaginatedResponse[LeaderboardEntryResponse],
)
async def get_server_leaderboard(
    ctx: ManagedServerDep,
    services: ServicesDep,
    page: int = Query(1, ge=1, description="Nomor halaman (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Jumlah item per halaman"),
    sort: Literal["balance", "xp"] = Query(
        "balance", description="Urutan berdasarkan balance atau xp"
    ),
) -> PaginatedResponse[LeaderboardEntryResponse]:
    items, total = await services.economy.paginated_leaderboard(
        ctx.id, by=sort, page=page, limit=limit
    )
    pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    offset = (page - 1) * limit
    return PaginatedResponse(
        items=[
            LeaderboardEntryResponse(
                user_id=str(entry.user_id),
                username=entry.username,
                balance=entry.balance,
                level=entry.level,
                xp=entry.xp,
                rank=offset + i + 1,
            )
            for i, entry in enumerate(items)
        ],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@router.get(
    "/{server_id}/moderation/logs",
    summary="Log moderasi server",
    response_model=PaginatedResponse[ModLogEntryResponse],
)
async def get_server_mod_logs(
    ctx: ManagedServerDep,
    services: ServicesDep,
    page: int = Query(1, ge=1, description="Nomor halaman (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Jumlah item per halaman"),
    target_id: int | None = Query(None, description="Filter ID target opsional"),
) -> PaginatedResponse[ModLogEntryResponse]:
    items, total = await services.moderation.paginated_logs(
        ctx.id, page=page, limit=limit, target_id=target_id
    )
    pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    return PaginatedResponse(
        items=[
            ModLogEntryResponse(
                id=item.id,
                action=item.action,
                moderator_id=str(item.mod_id) if item.mod_id is not None else "",
                moderator_name=item.mod_name,
                target_id=str(item.target_id),
                target_name=item.target_name,
                reason=item.reason,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )


@router.get(
    "/{server_id}/moderation/warnings",
    summary="Daftar peringatan server",
    response_model=PaginatedResponse[WarningResponse],
)
@router.get(
    "/{server_id}/warnings",
    summary="Daftar peringatan server (alias)",
    response_model=PaginatedResponse[WarningResponse],
    include_in_schema=False,
)
async def get_server_warnings(
    ctx: ManagedServerDep,
    services: ServicesDep,
    page: int = Query(1, ge=1, description="Nomor halaman (1-based)"),
    limit: int = Query(20, ge=1, le=100, description="Jumlah item per halaman"),
    user_id: int | None = Query(None, description="Filter ID user opsional"),
) -> PaginatedResponse[WarningResponse]:
    items, total = await services.moderation.paginated_warnings(
        ctx.id, page=page, limit=limit, user_id=user_id
    )
    pages = max(1, math.ceil(total / limit)) if total > 0 else 1
    return PaginatedResponse(
        items=[
            WarningResponse(
                id=item.id,
                user_id=str(item.user_id),
                username=item.username,
                moderator_id=str(item.mod_id),
                moderator_name=item.mod_name,
                reason=item.reason,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        page=page,
        limit=limit,
        pages=pages,
    )
