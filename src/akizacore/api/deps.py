from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
import structlog
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from akizacore.config import ApiSettings
from akizacore.core.exceptions import (
    NotFound,
    PermissionDenied,
    ProviderUnavailable,
    QuotaExceeded,
    Unauthorized,
)
from akizacore.models import Server, User, UserSession
from akizacore.services.container import Services

log = structlog.get_logger()

DISCORD_API_BASE = "https://discord.com/api/v10"
# Bitwise flags untuk izin Discord:
# MANAGE_GUILD: 0x20 (32)
# ADMINISTRATOR: 0x8 (8)
MANAGE_GUILD = 0x20
ADMINISTRATOR = 0x8


def has_manage_permission(guild: dict[str, Any]) -> bool:
    """Cek apakah user punya izin kelola server (Owner, Administrator, atau Manage Server)."""
    if guild.get("owner") is True:
        return True
    try:
        perms = int(guild.get("permissions", 0))
    except (ValueError, TypeError):
        perms = 0
    return bool(perms & (MANAGE_GUILD | ADMINISTRATOR))


async def fetch_user_guilds(
    session: UserSession,
    services: Services,
    http_client: httpx.AsyncClient | None,
    cache_ttl_s: int = 60,
) -> list[dict[str, Any]]:
    """Ambil daftar guild user dari Discord atau cache sesi database."""
    if session.cached_guilds is not None and session.guilds_cached_at is not None:
        age = (datetime.now(UTC) - session.guilds_cached_at).total_seconds()
        if age < cache_ttl_s:
            return session.cached_guilds

    async def _fetch(client: httpx.AsyncClient) -> httpx.Response:
        return await client.get(
            f"{DISCORD_API_BASE}/users/@me/guilds",
            headers={"Authorization": f"Bearer {session.access_token}"},
        )

    if http_client is not None:
        res = await _fetch(http_client)
    else:
        async with httpx.AsyncClient() as client:
            res = await _fetch(client)

    if res.status_code == 200:
        guilds: list[dict[str, Any]] = res.json()
        await services.auth.update_cached_guilds(session.id, guilds)
        session.cached_guilds = guilds
        session.guilds_cached_at = datetime.now(UTC)
        return guilds

    if res.status_code == 401:
        raise Unauthorized("Sesi Discord telah berakhir, silakan login ulang.")

    if res.status_code == 429:
        if session.cached_guilds is not None:
            return session.cached_guilds
        raise QuotaExceeded("Rate limit Discord tercapai, coba lagi sebentar.")

    log.warning("discord_guilds_fetch_failed", status=res.status_code, body=res.text)
    if session.cached_guilds is not None:
        return session.cached_guilds
    raise ProviderUnavailable("Gagal mengambil daftar server dari Discord.")


def get_services(request: Request) -> Services:
    """Service layer yang sama dengan bot. Router tidak boleh query database sendiri."""
    services: Services = request.app.state.services
    return services


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


def get_settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def get_http_client(request: Request) -> httpx.AsyncClient | None:
    return getattr(request.app.state, "http_client", None)


ServicesDep = Annotated[Services, Depends(get_services)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
SettingsDep = Annotated[ApiSettings, Depends(get_settings)]
HttpClientDep = Annotated[httpx.AsyncClient | None, Depends(get_http_client)]


async def get_current_session_and_user(
    request: Request,
    services: ServicesDep,
    settings: SettingsDep,
) -> tuple[UserSession, User]:
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise Unauthorized()
    res = await services.auth.get_session_and_user(session_id)
    if res is None:
        raise Unauthorized()
    return res


async def get_current_user(
    session_and_user: Annotated[tuple[UserSession, User], Depends(get_current_session_and_user)],
) -> User:
    return session_and_user[1]


async def get_current_session(
    session_and_user: Annotated[tuple[UserSession, User], Depends(get_current_session_and_user)],
) -> UserSession:
    return session_and_user[0]


CurrentUserDep = Annotated[User, Depends(get_current_user)]
CurrentSessionDep = Annotated[UserSession, Depends(get_current_session)]


@dataclass(frozen=True)
class ManagedServerContext:
    server: Server
    guild: dict[str, Any]

    @property
    def id(self) -> int:
        return self.server.id


async def get_managed_server(
    server_id: int,
    session: CurrentSessionDep,
    services: ServicesDep,
    settings: SettingsDep,
    http_client: HttpClientDep,
) -> ManagedServerContext:
    """Verifikasi bahwa user memiliki izin kelola pada server_id dan bot aktif di server tsb."""
    guilds = await fetch_user_guilds(
        session=session,
        services=services,
        http_client=http_client,
        cache_ttl_s=settings.guild_cache_ttl_s,
    )

    target_guild: dict[str, Any] | None = None
    for g in guilds:
        try:
            if int(g.get("id", 0)) == server_id:
                target_guild = g
                break
        except (ValueError, TypeError):
            continue

    if target_guild is None or not has_manage_permission(target_guild):
        raise PermissionDenied("Kamu tidak punya izin untuk mengelola server ini.")

    server = await services.onboarding.get_server(server_id)
    if server is None or not server.is_active:
        raise NotFound("Server tidak ditemukan atau bot belum ditambahkan.")

    return ManagedServerContext(server=server, guild=target_guild)


ManagedServerDep = Annotated[ManagedServerContext, Depends(get_managed_server)]
