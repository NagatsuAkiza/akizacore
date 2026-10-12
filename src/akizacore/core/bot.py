import discord
import structlog
from discord.ext import commands
from sqlalchemy import text

from akizacore.ai.config import AIConfig
from akizacore.ai.providers import build_llm
from akizacore.config import Settings
from akizacore.core.loader import load_cogs
from akizacore.core.tree import AkizaTree
from akizacore.database import build_engine, build_session_factory
from akizacore.services.container import Services
from akizacore.services.economy_config import EconomyConfig

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
        self.llm = build_llm(settings)
        self.services = Services.build(
            build_session_factory(self.engine),
            llm=self.llm,
            ai_config=AIConfig.from_settings(settings),
            economy_config=EconomyConfig.from_settings(settings),
        )

    async def setup_hook(self) -> None:
        await self._check_database()
        log.info("ai_provider", enabled=self.llm is not None)
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
        if self.llm is not None:
            await self.llm.aclose()
        await self.engine.dispose()
