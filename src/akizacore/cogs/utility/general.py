import discord
from discord import app_commands
from discord.ext import commands


class General(commands.Cog):
    """Command dasar. Cog = lapisan tipis; logika bisnis ada di services/."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Cek latensi bot")
    async def ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"Pong! {round(self.bot.latency * 1000)} ms")

    @app_commands.command(name="userinfo", description="Info tentang seorang member")
    @app_commands.describe(member="Member yang ingin dilihat (default: kamu)")
    @app_commands.guild_only()
    async def userinfo(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        target = member or interaction.user
        assert isinstance(target, discord.Member)
        embed = discord.Embed(title=str(target), color=target.color)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=str(target.id))
        embed.add_field(name="Akun dibuat", value=discord.utils.format_dt(target.created_at, "R"))
        if target.joined_at:
            embed.add_field(
                name="Gabung server", value=discord.utils.format_dt(target.joined_at, "R")
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Statistik server ini")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        embed = discord.Embed(title=guild.name)
        embed.add_field(name="Member", value=str(guild.member_count))
        embed.add_field(name="Channel", value=str(len(guild.channels)))
        embed.add_field(name="Role", value=str(len(guild.roles)))
        embed.add_field(name="Dibuat", value=discord.utils.format_dt(guild.created_at, "R"))
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
