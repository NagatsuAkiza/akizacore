import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from akizacore.api.deps import (
    CurrentSessionDep,
    HttpClientDep,
    ManagedServerDep,
    ServicesDep,
    SettingsDep,
    fetch_user_guilds,
    has_manage_permission,
)

log = structlog.get_logger()
router = APIRouter(prefix="/servers", tags=["servers"])


class ServerResponse(BaseModel):
    id: str
    name: str
    icon: str | None = None
    owner: bool = False
    bot_active: bool = False


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
