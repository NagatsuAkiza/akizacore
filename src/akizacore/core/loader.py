import pkgutil

import structlog
from discord.ext import commands

import akizacore.cogs as cogs_pkg

log = structlog.get_logger()


async def load_cogs(bot: commands.Bot) -> None:
    """Muat otomatis semua modul di akizacore/cogs/** yang punya fungsi setup()."""
    for mod in pkgutil.walk_packages(cogs_pkg.__path__, prefix=f"{cogs_pkg.__name__}."):
        if mod.ispkg or mod.name.rsplit(".", 1)[-1].startswith("_"):
            continue
        await bot.load_extension(mod.name)
        log.info("cog_loaded", cog=mod.name)
