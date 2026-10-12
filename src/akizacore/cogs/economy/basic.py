from typing import cast

import discord
import structlog
from discord import app_commands
from discord.ext import commands

from akizacore.cogs.economy._common import ensure_human, level_note, require_economy
from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import AkizaError
from akizacore.utils.converters import to_guild_info, to_user_info

log = structlog.get_logger()


class EconomyBasic(commands.Cog):
    """Command ekonomi dasar. Aturan bisnis ada di EconomyService."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @app_commands.command(name="balance", description="Lihat saldo, XP, dan level")
    @app_commands.describe(member="Member yang ingin dilihat (default: kamu)")
    @app_commands.guild_only()
    async def balance(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        guild_id = await require_economy(self.bot, interaction)
        target = member or interaction.user
        assert isinstance(target, discord.Member)
        await ensure_human(self.bot, target)
        p = await self.bot.services.economy.profile(guild_id, target.id)
        await interaction.response.send_message(
            f"**{target.display_name}**\n"
            f"Saldo: **{p.balance}** koin\n"
            f"Level **{p.level}** ({p.xp_into_level}/{p.xp_needed} XP)",
            ephemeral=member is None,
        )

    @app_commands.command(name="daily", description="Ambil hadiah harian")
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction) -> None:
        guild_id = await require_economy(self.bot, interaction)
        r = await self.bot.services.economy.daily(guild_id, interaction.user.id)
        await interaction.response.send_message(
            f"Kamu mendapat **{r.amount}** koin dan {r.xp_gained} XP. Saldo: **{r.balance}**."
            + level_note(r.leveled_up, r.level, r.bonus_coins)
        )

    @app_commands.command(name="work", description="Bekerja untuk mendapat koin (ada cooldown)")
    @app_commands.guild_only()
    async def work(self, interaction: discord.Interaction) -> None:
        guild_id = await require_economy(self.bot, interaction)
        r = await self.bot.services.economy.work(guild_id, interaction.user.id)
        await interaction.response.send_message(
            f"Kamu bekerja {r.job} dan mendapat **{r.amount}** koin. Saldo: **{r.balance}**."
            + level_note(r.leveled_up, r.level, r.bonus_coins)
        )

    @app_commands.command(name="leaderboard", description="Peringkat teratas di server ini")
    @app_commands.describe(by="Urutkan berdasarkan koin atau XP")
    @app_commands.choices(
        by=[
            app_commands.Choice(name="Koin", value="balance"),
            app_commands.Choice(name="XP", value="xp"),
        ]
    )
    @app_commands.guild_only()
    async def leaderboard(
        self, interaction: discord.Interaction, by: app_commands.Choice[str] | None = None
    ) -> None:
        guild_id = await require_economy(self.bot, interaction)
        key = by.value if by else "balance"
        entries = await self.bot.services.economy.leaderboard(guild_id, by=key, limit=10)
        if not entries:
            await interaction.response.send_message("Belum ada data peringkat.", ephemeral=True)
            return
        lines = [
            f"{i}. **{e.username}** - "
            + (f"{e.xp} XP (level {e.level})" if key == "xp" else f"{e.balance} koin")
            for i, e in enumerate(entries, start=1)
        ]
        title = "Peringkat XP" if key == "xp" else "Peringkat Koin"
        await interaction.response.send_message(
            embed=discord.Embed(title=title, description="\n".join(lines))
        )

    @app_commands.command(
        name="transfer", description="Kirim koin ke member lain (ada batas harian)"
    )
    @app_commands.describe(member="Penerima", amount="Jumlah koin")
    @app_commands.guild_only()
    async def transfer(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        guild_id = await require_economy(self.bot, interaction)
        await ensure_human(self.bot, member)
        r = await self.bot.services.economy.transfer(
            guild_id, interaction.user.id, member.id, amount
        )
        await interaction.response.send_message(
            f"Kamu mengirim **{r.amount}** koin ke {member.display_name}. "
            f"Saldo kamu: **{r.sender_balance}**."
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """XP dari chat: cek cooldown di memori dulu agar tidak membebani database."""
        if message.author.bot or message.guild is None:
            return
        economy = self.bot.services.economy
        if not economy.message_xp_ready(message.guild.id, message.author.id):
            return
        try:
            await self.bot.services.onboarding.ensure_context(
                to_user_info(message.author), to_guild_info(message.guild)
            )
            await self.bot.services.settings.require_feature(message.guild.id, "economy")
            result = await economy.award_message_xp(message.guild.id, message.author.id)
        except AkizaError:
            return  # modul mati / server belum terdaftar: abaikan diam-diam
        except Exception:
            log.exception("message_xp_error", guild_id=message.guild.id)
            return
        if result is not None and result.leveled_up:
            await message.channel.send(
                f"{message.author.display_name} naik ke **level {result.level}**! "
                f"Bonus {result.bonus_coins} koin."
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyBasic(cast(AkizaBot, bot)))
