<#
 AkizaCore - Fase 2: Database + User
 Jalankan DARI DALAM folder project (yang berisi pyproject.toml):
   cd D:\Project\AkizaCore
   powershell -ExecutionPolicy Bypass -File ..\phase2-database.ps1
 Prasyarat: Docker Desktop menyala, Fase 1 sudah selesai.
 Opsi:
   -NoCommit      buat file saja, tanpa git commit
   -StartAt 4     lanjutkan dari scope tertentu bila script berhenti di tengah
#>
param(
    [switch]$NoCommit,
    [int]$StartAt = 1
)

$ErrorActionPreference = "Stop"

# ---------- Helper ----------
function Write-File([string]$Path, [string]$Content) {
    $full = Join-Path (Get-Location) $Path
    $dir = Split-Path $full -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText($full, $Content.Replace("`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))
}

function Edit-File([string]$Path, [string]$Old, [string]$New) {
    $full = Join-Path (Get-Location) $Path
    $text = [System.IO.File]::ReadAllText($full).Replace("`r`n", "`n")
    $Old = $Old.Replace("`r`n", "`n"); $New = $New.Replace("`r`n", "`n")
    if ($text.Contains($New)) { return }
    if (-not $text.Contains($Old)) { throw "Teks tidak ditemukan di ${Path}: $Old" }
    [System.IO.File]::WriteAllText($full, $text.Replace($Old, $New), (New-Object System.Text.UTF8Encoding($false)))
}

function Assert-Ok([string]$What) {
    if ($LASTEXITCODE -ne 0) { throw "Gagal: $What (exit code $LASTEXITCODE)" }
}

function Complete-Scope([string]$Message) {
    git add -A
    $changes = git status --porcelain
    if (-not $changes) { Write-Host "  [skip] tidak ada perubahan: $Message" -ForegroundColor Yellow; return }
    if ($NoCommit) {
        Write-Host "  [skip commit] git add -A; git commit -m `"$Message`"" -ForegroundColor Yellow
    } else {
        git commit -m $Message | Out-Null
        Assert-Ok "git commit"
        Write-Host "  [commit] $Message" -ForegroundColor Green
    }
}

function Write-Scope([string]$Title) { Write-Host ""; Write-Host "=== $Title ===" -ForegroundColor Cyan }

function Invoke-Lint {
    & .\.venv\Scripts\ruff.exe check . --fix; Assert-Ok "ruff check"
    & .\.venv\Scripts\ruff.exe format .; Assert-Ok "ruff format"
}

function Invoke-Mypy { & .\.venv\Scripts\mypy.exe src; Assert-Ok "mypy" }

function Wait-Postgres {
    for ($i = 0; $i -lt 40; $i++) {
        $status = ""
        try { $status = docker inspect -f "{{.State.Health.Status}}" akizacore-postgres 2>$null } catch { }
        if ($status -eq "healthy") { Write-Host "  PostgreSQL siap."; return }
        Start-Sleep -Seconds 2
    }
    throw "PostgreSQL tidak kunjung sehat. Cek: docker compose logs postgres (port 5432 mungkin bentrok dengan Postgres lokal)."
}

# ---------- Cek posisi ----------
if (-not (Test-Path "pyproject.toml") -or -not (Test-Path ".venv")) {
    throw "Jalankan script ini dari dalam folder project AkizaCore (yang berisi pyproject.toml dan .venv)."
}

# ==========================================================
# SCOPE 1: Engine + session async
# ==========================================================
if ($StartAt -le 1) {
    Write-Scope "Scope 1: Database engine dan session"
    & .\.venv\Scripts\python.exe -m pip install -e ".[db,dev]"; Assert-Ok "pip install db"

    Write-File "src/akizacore/database/base.py" @'
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Basis semua model SQLAlchemy."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
'@

    Write-File "src/akizacore/database/engine.py" @'
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def build_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(url, echo=echo, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
'@

    Write-File "src/akizacore/database/session.py" @'
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Unit of work: commit bila sukses, rollback otomatis bila ada exception."""
    async with factory() as session, session.begin():
        yield session
'@

    Write-File "src/akizacore/database/__init__.py" @'
from akizacore.database.base import Base, TimestampMixin
from akizacore.database.engine import build_engine, build_session_factory
from akizacore.database.session import session_scope

__all__ = ["Base", "TimestampMixin", "build_engine", "build_session_factory", "session_scope"]
'@

    # Settings: tambah DatabaseSettings agar alembic tidak butuh DISCORD_TOKEN
    Write-File "src/akizacore/config/settings.py" @'
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+asyncpg://akiza:akiza@localhost:5432/akizacore"

_ENV = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class DatabaseSettings(BaseSettings):
    """Hanya URL database. Dipakai alembic dan test tanpa perlu token Discord."""

    model_config = _ENV

    database_url: str = DEFAULT_DATABASE_URL


class Settings(BaseSettings):
    """Semua konfigurasi dibaca dari environment / file .env."""

    model_config = _ENV

    environment: Literal["dev", "prod"] = "dev"
    log_level: str = "INFO"

    discord_token: SecretStr
    dev_guild_id: int | None = None

    database_url: str = DEFAULT_DATABASE_URL

    ai_base_url: str | None = None
    ai_api_key: SecretStr | None = None
    ai_model_fast: str | None = None
    ai_model_smart: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
'@

    Write-File "src/akizacore/config/__init__.py" @'
from akizacore.config.settings import DatabaseSettings, Settings, get_settings

__all__ = ["DatabaseSettings", "Settings", "get_settings"]
'@

    Invoke-Lint
    Complete-Scope "feat(database): engine dan session SQLAlchemy async"
}

# ==========================================================
# SCOPE 2: Models
# ==========================================================
if ($StartAt -le 2) {
    Write-Scope "Scope 2: Models"

    Write-File "src/akizacore/models/user.py" @'
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from akizacore.database.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(100))
    avatar: Mapped[str | None] = mapped_column(String(255), default=None)


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(10), default="id", server_default="id")
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Jakarta", server_default="Asia/Jakarta"
    )
    ai_prefs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    ai_opt_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
'@

    Write-File "src/akizacore/models/server.py" @'
from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from akizacore.database.base import Base, TimestampMixin


class Server(TimestampMixin, Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class ServerSettings(TimestampMixin, Base):
    __tablename__ = "settings"

    server_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True
    )
    log_channel_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    welcome_channel_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    autorole_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    ai_persona: Mapped[str | None] = mapped_column(Text, default=None)
    features: Mapped[dict[str, bool]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
'@

    Write-File "src/akizacore/models/__init__.py" @'
from akizacore.models.server import Server, ServerSettings
from akizacore.models.user import User, UserProfile

__all__ = ["Server", "ServerSettings", "User", "UserProfile"]
'@

    Invoke-Lint
    Invoke-Mypy
    Complete-Scope "feat(models): model users, servers, settings, user_profiles"
}

# ==========================================================
# SCOPE 3: Alembic + migrasi awal (butuh Docker)
# ==========================================================
if ($StartAt -le 3) {
    Write-Scope "Scope 3: Alembic dan migrasi awal"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker belum terpasang / belum ada di PATH." }

    docker compose up -d; Assert-Ok "docker compose up"
    Wait-Postgres

    if (-not (Test-Path "alembic")) {
        & .\.venv\Scripts\alembic.exe init -t async alembic; Assert-Ok "alembic init"
    }

    Write-File "alembic/env.py" @'
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import akizacore.models  # noqa: F401  (daftarkan semua model ke metadata)
from akizacore.config import DatabaseSettings
from akizacore.database.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", DatabaseSettings().database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'@

    # Lint tidak memeriksa file migrasi hasil generate
    Edit-File "pyproject.toml" 'src = ["src", "tests"]' ('src = ["src", "tests"]' + "`n" + 'extend-exclude = ["alembic/versions"]')

    $existing = Get-ChildItem "alembic/versions" -Filter "*.py" -ErrorAction SilentlyContinue
    if (-not $existing) {
        & .\.venv\Scripts\alembic.exe revision --autogenerate -m "initial schema" --rev-id 0001; Assert-Ok "alembic revision"
        $mig = Get-ChildItem "alembic/versions" -Filter "0001*.py" | Select-Object -First 1
        if (-not (Select-String -Path $mig.FullName -Pattern "create_table" -Quiet)) {
            throw "Migrasi kosong (tidak ada create_table). Cek apakah akizacore.models ter-import di alembic/env.py."
        }
    }
    & .\.venv\Scripts\alembic.exe upgrade head; Assert-Ok "alembic upgrade head"

    Invoke-Lint
    Complete-Scope "build(alembic): inisialisasi migrasi dan migrasi awal"
}

# ==========================================================
# SCOPE 4: Repository
# ==========================================================
if ($StartAt -le 4) {
    Write-Scope "Scope 4: Repository"

    Write-File "src/akizacore/database/repositories/users.py" @'
from sqlalchemy import func, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import User, UserProfile


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id, populate_existing=True)

    async def upsert(self, user_id: int, username: str, avatar: str | None) -> None:
        stmt = insert(User).values(id=user_id, username=username, avatar=avatar)
        stmt = stmt.on_conflict_do_update(
            index_elements=[User.id],
            set_={
                "username": stmt.excluded.username,
                "avatar": stmt.excluded.avatar,
                "updated_at": func.now(),
            },
            # hanya tulis bila ada yang berubah (hemat write di tiap command)
            where=or_(
                User.username != stmt.excluded.username,
                User.avatar.is_distinct_from(stmt.excluded.avatar),
            ),
        )
        await self.session.execute(stmt)

    async def ensure_profile(self, user_id: int) -> None:
        stmt = (
            insert(UserProfile)
            .values(user_id=user_id)
            .on_conflict_do_nothing(index_elements=[UserProfile.user_id])
        )
        await self.session.execute(stmt)

    async def get_profile(self, user_id: int) -> UserProfile | None:
        return await self.session.get(UserProfile, user_id, populate_existing=True)
'@

    Write-File "src/akizacore/database/repositories/servers.py" @'
from sqlalchemy import func, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import Server


class ServerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, server_id: int) -> Server | None:
        return await self.session.get(Server, server_id, populate_existing=True)

    async def upsert(self, server_id: int, name: str, owner_id: int | None) -> None:
        """Daftarkan server; bila sudah ada, perbarui nama/owner dan aktifkan kembali."""
        stmt = insert(Server).values(id=server_id, name=name, owner_id=owner_id, is_active=True)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Server.id],
            set_={
                "name": stmt.excluded.name,
                "owner_id": stmt.excluded.owner_id,
                "is_active": True,
                "updated_at": func.now(),
            },
            where=or_(
                Server.name != stmt.excluded.name,
                Server.owner_id.is_distinct_from(stmt.excluded.owner_id),
                Server.is_active.is_(False),
            ),
        )
        await self.session.execute(stmt)

    async def deactivate(self, server_id: int) -> None:
        await self.session.execute(
            update(Server).where(Server.id == server_id).values(is_active=False)
        )
'@

    Write-File "src/akizacore/database/repositories/settings.py" @'
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import ServerSettings


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, server_id: int) -> ServerSettings | None:
        return await self.session.get(ServerSettings, server_id, populate_existing=True)

    async def ensure(self, server_id: int, features: dict[str, bool]) -> None:
        """Buat baris settings bila belum ada. Tidak menimpa konfigurasi yang sudah ada."""
        stmt = (
            insert(ServerSettings)
            .values(server_id=server_id, features=features)
            .on_conflict_do_nothing(index_elements=[ServerSettings.server_id])
        )
        await self.session.execute(stmt)

    async def update(self, server_id: int, values: dict[str, Any]) -> ServerSettings | None:
        row = await self.get(server_id)
        if row is None:
            return None
        for key, value in values.items():
            setattr(row, key, value)
        await self.session.flush()
        return row
'@

    Write-File "src/akizacore/database/repositories/__init__.py" @'
from akizacore.database.repositories.servers import ServerRepository
from akizacore.database.repositories.settings import SettingsRepository
from akizacore.database.repositories.users import UserRepository

__all__ = ["ServerRepository", "SettingsRepository", "UserRepository"]
'@

    Invoke-Lint
    Invoke-Mypy
    Complete-Scope "feat(repository): repository users, servers, dan settings"
}

# ==========================================================
# SCOPE 5: Schemas + Services (tanpa import discord)
# ==========================================================
if ($StartAt -le 5) {
    Write-Scope "Scope 5: Services"

    Edit-File "src/akizacore/core/exceptions.py" "class PermissionDenied(AkizaError):" @'
class ValidationFailed(AkizaError):
    user_message = "Input tidak valid."
    http_status = 400


class PermissionDenied(AkizaError):
'@

    Write-File "src/akizacore/schemas/discord.py" @'
from pydantic import BaseModel, ConfigDict


class UserInfo(BaseModel):
    """Data user dari Discord, sudah dinetralkan agar service tidak perlu import discord."""

    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    avatar: str | None = None


class GuildInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    owner_id: int | None = None
'@

    Write-File "src/akizacore/schemas/settings.py" @'
from pydantic import BaseModel, ConfigDict, field_validator

FEATURES: tuple[str, ...] = ("ai", "economy", "fun", "utility", "moderation")

# AI default mati: admin harus menyalakan sendiri (kontrol biaya)
DEFAULT_FEATURES: dict[str, bool] = {
    "ai": False,
    "economy": True,
    "fun": True,
    "utility": True,
    "moderation": True,
}


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    server_id: int
    log_channel_id: int | None = None
    welcome_channel_id: int | None = None
    autorole_id: int | None = None
    ai_persona: str | None = None
    features: dict[str, bool] = {}

    @field_validator("features")
    @classmethod
    def _merge_defaults(cls, value: dict[str, bool]) -> dict[str, bool]:
        # fitur baru yang belum tersimpan di DB otomatis memakai nilai default
        return {**DEFAULT_FEATURES, **value}


class SettingsUpdate(BaseModel):
    """Hanya field yang diisi yang diubah (gunakan model_dump(exclude_unset=True))."""

    log_channel_id: int | None = None
    welcome_channel_id: int | None = None
    autorole_id: int | None = None
    ai_persona: str | None = None
'@

    Write-File "src/akizacore/services/onboarding.py" @'
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.database.repositories import ServerRepository, SettingsRepository, UserRepository
from akizacore.database.session import session_scope
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.schemas.settings import DEFAULT_FEATURES


class OnboardingService:
    """Mendaftarkan guild dan user ke database (idempotent, aman dipanggil berulang)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def register_guild(self, guild: GuildInfo) -> None:
        async with session_scope(self._sf) as session:
            await self._register_guild(session, guild)

    async def sync_guilds(self, guilds: Sequence[GuildInfo]) -> None:
        async with session_scope(self._sf) as session:
            for guild in guilds:
                await self._register_guild(session, guild)

    async def deactivate_guild(self, guild_id: int) -> None:
        async with session_scope(self._sf) as session:
            await ServerRepository(session).deactivate(guild_id)

    async def ensure_user(self, user: UserInfo) -> None:
        async with session_scope(self._sf) as session:
            await self._ensure_user(session, user)

    async def ensure_context(self, user: UserInfo, guild: GuildInfo | None) -> None:
        """Dipanggil sebelum setiap command: pastikan user (dan guild) ada di database."""
        async with session_scope(self._sf) as session:
            await self._ensure_user(session, user)
            if guild is not None:
                await self._register_guild(session, guild)

    @staticmethod
    async def _register_guild(session: AsyncSession, guild: GuildInfo) -> None:
        await ServerRepository(session).upsert(guild.id, guild.name, guild.owner_id)
        await SettingsRepository(session).ensure(guild.id, dict(DEFAULT_FEATURES))

    @staticmethod
    async def _ensure_user(session: AsyncSession, user: UserInfo) -> None:
        repo = UserRepository(session)
        await repo.upsert(user.id, user.username, user.avatar)
        await repo.ensure_profile(user.id)
'@

    Write-File "src/akizacore/services/settings.py" @'
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import NotFound, ValidationFailed
from akizacore.database.repositories import SettingsRepository
from akizacore.database.session import session_scope
from akizacore.schemas.settings import FEATURES, SettingsRead, SettingsUpdate

_NOT_REGISTERED = "Server belum terdaftar. Coba ulangi command."


class SettingsService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get(self, server_id: int) -> SettingsRead:
        async with session_scope(self._sf) as session:
            row = await SettingsRepository(session).get(server_id)
            if row is None:
                raise NotFound(_NOT_REGISTERED)
            return SettingsRead.model_validate(row)

    async def update(self, server_id: int, data: SettingsUpdate) -> SettingsRead:
        values = data.model_dump(exclude_unset=True)
        async with session_scope(self._sf) as session:
            row = await SettingsRepository(session).update(server_id, values)
            if row is None:
                raise NotFound(_NOT_REGISTERED)
            return SettingsRead.model_validate(row)

    async def set_feature(self, server_id: int, feature: str, enabled: bool) -> SettingsRead:
        if feature not in FEATURES:
            raise ValidationFailed(f"Fitur tidak dikenal: {feature}")
        async with session_scope(self._sf) as session:
            repo = SettingsRepository(session)
            current = await repo.get(server_id)
            if current is None:
                raise NotFound(_NOT_REGISTERED)
            merged = {**current.features, feature: enabled}
            row = await repo.update(server_id, {"features": merged})
            if row is None:
                raise NotFound(_NOT_REGISTERED)
            return SettingsRead.model_validate(row)
'@

    Write-File "src/akizacore/services/container.py" @'
from dataclasses import dataclass
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.services.onboarding import OnboardingService
from akizacore.services.settings import SettingsService


@dataclass(frozen=True)
class Services:
    """Kumpulan service. Dipakai bot sekarang dan FastAPI di Fase 6."""

    onboarding: OnboardingService
    settings: SettingsService

    @classmethod
    def build(cls, session_factory: async_sessionmaker[AsyncSession]) -> Self:
        return cls(
            onboarding=OnboardingService(session_factory),
            settings=SettingsService(session_factory),
        )
'@

    Invoke-Lint
    Invoke-Mypy
    Complete-Scope "feat(services): onboarding guild dan server settings service"
}

# ==========================================================
# SCOPE 6: Integrasi bot + /setup
# ==========================================================
if ($StartAt -le 6) {
    Write-Scope "Scope 6: Integrasi bot dan command /setup"

    Write-File "src/akizacore/utils/converters.py" @'
import discord

from akizacore.schemas.discord import GuildInfo, UserInfo


def to_user_info(user: discord.User | discord.Member) -> UserInfo:
    return UserInfo(id=user.id, username=user.name, avatar=user.avatar.key if user.avatar else None)


def to_guild_info(guild: discord.Guild) -> GuildInfo:
    return GuildInfo(id=guild.id, name=guild.name, owner_id=guild.owner_id)
'@

    Write-File "src/akizacore/core/tree.py" @'
from typing import TYPE_CHECKING, cast

import discord
import structlog
from discord import app_commands

from akizacore.core.exceptions import AkizaError
from akizacore.utils.converters import to_guild_info, to_user_info

if TYPE_CHECKING:
    from akizacore.core.bot import AkizaBot

log = structlog.get_logger()


class AkizaTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sebelum setiap command: pastikan user dan guild sudah terdaftar di database."""
        bot = cast("AkizaBot", interaction.client)
        guild = interaction.guild
        await bot.services.onboarding.ensure_context(
            to_user_info(interaction.user),
            to_guild_info(guild) if guild else None,
        )
        return True

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, AkizaError):
            message = original.user_message
        elif isinstance(error, app_commands.MissingPermissions):
            message = "Kamu butuh izin Manage Server untuk command ini."
        elif isinstance(error, app_commands.CheckFailure):
            message = "Kamu tidak boleh memakai command ini."
        else:
            log.exception("command_error", command=getattr(interaction.command, "name", None))
            message = "Terjadi kesalahan internal."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
'@

    Write-File "src/akizacore/core/bot.py" @'
import discord
import structlog
from discord.ext import commands
from sqlalchemy import text

from akizacore.config import Settings
from akizacore.core.loader import load_cogs
from akizacore.core.tree import AkizaTree
from akizacore.database import build_engine, build_session_factory
from akizacore.services.container import Services

log = structlog.get_logger()


class AkizaBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # privileged: aktifkan di Developer Portal
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
            tree_cls=AkizaTree,
        )
        self.settings = settings
        self.engine = build_engine(settings.database_url)
        self.services = Services.build(build_session_factory(self.engine))

    async def setup_hook(self) -> None:
        await self._check_database()
        await load_cogs(self)
        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("commands_synced", scope="guild", guild_id=self.settings.dev_guild_id)
        else:
            await self.tree.sync()
            log.info("commands_synced", scope="global")

    async def _check_database(self) -> None:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            log.error("database_unreachable", hint="jalankan: docker compose up -d")
            raise
        log.info("database_connected")

    async def on_ready(self) -> None:
        log.info("bot_ready", user=str(self.user), guilds=len(self.guilds))

    async def close(self) -> None:
        await super().close()
        await self.engine.dispose()
'@

    Write-File "src/akizacore/cogs/settings/guild_events.py" @'
from typing import cast

import discord
import structlog
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.utils.converters import to_guild_info

log = structlog.get_logger()


class GuildEvents(commands.Cog):
    """Sinkronisasi guild ke database saat bot join/leave/start."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot
        self._synced = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._synced:
            return
        await self.bot.services.onboarding.sync_guilds([to_guild_info(g) for g in self.bot.guilds])
        self._synced = True
        log.info("guilds_synced", count=len(self.bot.guilds))

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self.bot.services.onboarding.register_guild(to_guild_info(guild))
        log.info("guild_joined", guild_id=guild.id)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        await self.bot.services.onboarding.register_guild(to_guild_info(after))

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.bot.services.onboarding.deactivate_guild(guild.id)
        log.info("guild_removed", guild_id=guild.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GuildEvents(cast(AkizaBot, bot)))
'@

    Write-File "src/akizacore/cogs/settings/setup.py" @'
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.schemas.settings import FEATURES, SettingsUpdate

ON = "\u2705"
OFF = "\u274c"


def _channel(channel_id: int | None) -> str:
    return f"<#{channel_id}>" if channel_id else "-"


def _role(role_id: int | None) -> str:
    return f"<@&{role_id}>" if role_id else "-"


class SetupCog(commands.Cog):
    """Konfigurasi server. Cog tipis: semua logika ada di SettingsService."""

    setup_group = app_commands.Group(
        name="setup",
        description="Konfigurasi bot untuk server ini",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @setup_group.command(name="view", description="Lihat konfigurasi server saat ini")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def view(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        data = await self.bot.services.settings.get(interaction.guild.id)
        embed = discord.Embed(title=f"Konfigurasi {interaction.guild.name}")
        embed.add_field(name="Log channel", value=_channel(data.log_channel_id))
        embed.add_field(name="Welcome channel", value=_channel(data.welcome_channel_id))
        embed.add_field(name="Autorole", value=_role(data.autorole_id))
        features = "\n".join(f"{ON if data.features.get(f) else OFF} {f}" for f in FEATURES)
        embed.add_field(name="Fitur", value=features, inline=False)
        embed.add_field(name="AI persona", value=data.ai_persona or "-", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @setup_group.command(name="channels", description="Atur channel log, welcome, dan autorole")
    @app_commands.describe(
        log_channel="Channel untuk log moderasi",
        welcome_channel="Channel untuk pesan sambutan",
        autorole="Role otomatis untuk member baru",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def channels(
        self,
        interaction: discord.Interaction,
        log_channel: discord.TextChannel | None = None,
        welcome_channel: discord.TextChannel | None = None,
        autorole: discord.Role | None = None,
    ) -> None:
        assert interaction.guild is not None
        fields: dict[str, int] = {}
        if log_channel:
            fields["log_channel_id"] = log_channel.id
        if welcome_channel:
            fields["welcome_channel_id"] = welcome_channel.id
        if autorole:
            fields["autorole_id"] = autorole.id
        if not fields:
            await interaction.response.send_message("Isi minimal satu opsi.", ephemeral=True)
            return
        await self.bot.services.settings.update(interaction.guild.id, SettingsUpdate(**fields))
        await interaction.response.send_message("Konfigurasi disimpan.", ephemeral=True)

    @setup_group.command(name="feature", description="Nyalakan / matikan modul")
    @app_commands.describe(feature="Modul yang diatur", enabled="Aktif atau tidak")
    @app_commands.choices(feature=[app_commands.Choice(name=f, value=f) for f in FEATURES])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def feature(
        self,
        interaction: discord.Interaction,
        feature: app_commands.Choice[str],
        enabled: bool,
    ) -> None:
        assert interaction.guild is not None
        await self.bot.services.settings.set_feature(
            interaction.guild.id, feature.value, enabled
        )
        state = "diaktifkan" if enabled else "dimatikan"
        await interaction.response.send_message(
            f"Modul **{feature.value}** {state}.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(cast(AkizaBot, bot)))
'@

    Invoke-Lint
    Invoke-Mypy
    Complete-Scope "feat(settings): command /setup dan integrasi database ke bot"
}

# ==========================================================
# SCOPE 7: Test (integrasi ke PostgreSQL)
# ==========================================================
if ($StartAt -le 7) {
    Write-Scope "Scope 7: Test services dan repository"

    Write-File "tests/conftest.py" @'
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from akizacore.config import DatabaseSettings
from akizacore.database import Base, build_session_factory
import akizacore.models  # noqa: F401

TEST_DB = "akizacore_test"


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Database test terpisah (akizacore_test), dibuat otomatis dan di-reset tiap test."""
    base_url = make_url(DatabaseSettings().database_url)
    admin = create_async_engine(
        base_url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    except Exception as exc:
        pytest.skip(f"PostgreSQL tidak tersedia (jalankan: docker compose up -d): {exc}")
    finally:
        await admin.dispose()

    engine = create_async_engine(base_url.set(database=TEST_DB), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield build_session_factory(engine)
    await engine.dispose()
'@

    Write-File "tests/test_schemas.py" @'
from akizacore.schemas.settings import DEFAULT_FEATURES, SettingsRead, SettingsUpdate


def test_features_merge_with_defaults() -> None:
    data = SettingsRead(server_id=1, features={"ai": True})
    assert data.features["ai"] is True
    assert data.features["economy"] is True
    assert set(data.features) == set(DEFAULT_FEATURES)


def test_update_only_dumps_provided_fields() -> None:
    update = SettingsUpdate(log_channel_id=123)
    assert update.model_dump(exclude_unset=True) == {"log_channel_id": 123}
'@

    Write-File "tests/test_onboarding.py" @'
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.models import Server, UserProfile
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.schemas.settings import SettingsUpdate
from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=111, name="Server A", owner_id=222)


async def test_register_guild_creates_server_and_default_settings(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)

    settings = await services.settings.get(GUILD.id)
    assert settings.features["ai"] is False
    assert settings.features["economy"] is True


async def test_register_guild_is_idempotent_and_keeps_settings(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)
    await services.settings.update(GUILD.id, SettingsUpdate(log_channel_id=999))

    await services.onboarding.register_guild(GuildInfo(id=111, name="Nama Baru", owner_id=222))

    settings = await services.settings.get(GUILD.id)
    assert settings.log_channel_id == 999
    async with session_factory() as session:
        server = await session.get(Server, GUILD.id)
        assert server is not None
        assert server.name == "Nama Baru"


async def test_deactivate_then_rejoin_reactivates(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)
    await services.onboarding.deactivate_guild(GUILD.id)
    async with session_factory() as session:
        server = await session.get(Server, GUILD.id)
        assert server is not None and server.is_active is False

    await services.onboarding.register_guild(GUILD)
    async with session_factory() as session:
        server = await session.get(Server, GUILD.id, populate_existing=True)
        assert server is not None and server.is_active is True


async def test_ensure_user_creates_profile_with_defaults(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    user = UserInfo(id=555, username="tester", avatar=None)
    await services.onboarding.ensure_user(user)
    await services.onboarding.ensure_user(user)  # kedua kali tidak boleh error

    async with session_factory() as session:
        profile = await session.get(UserProfile, 555)
        assert profile is not None
        assert profile.language == "id"
        assert profile.ai_opt_out is False


async def test_ensure_context_registers_user_and_guild(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.ensure_context(UserInfo(id=1, username="a"), GUILD)
    assert (await services.settings.get(GUILD.id)).server_id == GUILD.id
'@

    Write-File "tests/test_settings_service.py" @'
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import NotFound, ValidationFailed
from akizacore.schemas.discord import GuildInfo
from akizacore.schemas.settings import SettingsUpdate
from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]
GUILD = GuildInfo(id=10, name="Test", owner_id=1)


async def test_update_channels(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)

    result = await services.settings.update(
        GUILD.id, SettingsUpdate(log_channel_id=1, autorole_id=2)
    )
    assert result.log_channel_id == 1
    assert result.autorole_id == 2
    assert result.welcome_channel_id is None


async def test_set_feature_toggles_only_that_feature(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)

    result = await services.settings.set_feature(GUILD.id, "ai", True)
    assert result.features["ai"] is True
    assert result.features["economy"] is True


async def test_set_feature_rejects_unknown_feature(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    await services.onboarding.register_guild(GUILD)
    with pytest.raises(ValidationFailed):
        await services.settings.set_feature(GUILD.id, "tidak-ada", True)


async def test_get_unknown_server_raises_not_found(session_factory: Factory) -> None:
    services = Services.build(session_factory)
    with pytest.raises(NotFound):
        await services.settings.get(424242)
'@

    docker compose up -d; Assert-Ok "docker compose up"
    Wait-Postgres
    Invoke-Lint
    Invoke-Mypy
    & .\.venv\Scripts\python.exe -m pytest -q; Assert-Ok "pytest"
    Complete-Scope "test: integrasi services dan repository ke PostgreSQL"
}

Write-Host ""
Write-Host "Fase 2 selesai." -ForegroundColor Green
Write-Host "  Jalankan bot : python -m akizacore.main"
Write-Host "  Tes Discord  : /setup view , /setup channels , /setup feature"
Write-Host "  Lihat data   : docker exec -it akizacore-postgres psql -U akiza -d akizacore -c 'select * from settings;'"
git log --oneline