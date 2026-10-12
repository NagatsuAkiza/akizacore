import contextlib
from typing import cast

from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import NotFound


class PrefixHelpCog(commands.Cog):
    """Command teks minimal untuk menemukan command slash dan prefix."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @commands.command(name="help")
    async def help(self, ctx: commands.Context[AkizaBot]) -> None:
        prefix = "!"
        if ctx.guild is not None:
            with contextlib.suppress(NotFound):
                prefix = (await self.bot.services.settings.get(ctx.guild.id)).prefix
        await ctx.send(
            f"Gunakan `/help` untuk daftar command berdasarkan fitur. "
            f"Prefix aktif: `{prefix}`. Prefix saat ini hanya menyediakan `{prefix}help`."
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PrefixHelpCog(cast(AkizaBot, bot)))
