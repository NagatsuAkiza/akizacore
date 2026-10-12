from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.schemas.settings import FEATURES, SettingsUpdate

ON = "\u2705"
OFF = "\u274c"


async def _manage_guild_or_owner(interaction: discord.Interaction) -> bool:
    bot = cast(AkizaBot, interaction.client)
    return bot.is_owner_user(interaction.user.id) or (
        isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.manage_guild
    )


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
    )

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @setup_group.command(name="view", description="Lihat konfigurasi server saat ini")
    @app_commands.check(_manage_guild_or_owner)
    async def view(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        data = await self.bot.services.settings.get(interaction.guild.id)
        embed = discord.Embed(title=f"Konfigurasi {interaction.guild.name}")
        embed.add_field(name="Log channel", value=_channel(data.log_channel_id))
        embed.add_field(name="Welcome channel", value=_channel(data.welcome_channel_id))
        embed.add_field(name="Autorole", value=_role(data.autorole_id))
        embed.add_field(name="Prefix", value=f"`{data.prefix}`")
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
    @app_commands.check(_manage_guild_or_owner)
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
        await self.bot.services.settings.update(
            interaction.guild.id, SettingsUpdate.model_validate(fields)
        )
        await interaction.response.send_message("Konfigurasi disimpan.", ephemeral=True)

    @setup_group.command(name="prefix", description="Atur prefix command teks bot")
    @app_commands.describe(prefix="Prefix 1-5 karakter tanpa spasi, contoh: ! atau ?")
    @app_commands.check(_manage_guild_or_owner)
    async def prefix(
        self, interaction: discord.Interaction, prefix: app_commands.Range[str, 1, 5]
    ) -> None:
        assert interaction.guild is not None
        data = SettingsUpdate(prefix=prefix)
        await self.bot.services.settings.update(interaction.guild.id, data)
        self.bot.invalidate_prefix(interaction.guild.id)
        await interaction.response.send_message(
            f"Prefix disimpan sebagai `{prefix}`. Gunakan `{prefix}help` untuk bantuan command teks.",
            ephemeral=True,
        )

    @setup_group.command(name="feature", description="Nyalakan / matikan modul")
    @app_commands.describe(feature="Modul yang diatur", enabled="Aktif atau tidak")
    @app_commands.choices(feature=[app_commands.Choice(name=f, value=f) for f in FEATURES])
    @app_commands.check(_manage_guild_or_owner)
    async def feature(
        self,
        interaction: discord.Interaction,
        feature: app_commands.Choice[str],
        enabled: bool,
    ) -> None:
        assert interaction.guild is not None
        await self.bot.services.settings.set_feature(interaction.guild.id, feature.value, enabled)
        state = "diaktifkan" if enabled else "dimatikan"
        await interaction.response.send_message(
            f"Modul **{feature.value}** {state}.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(cast(AkizaBot, bot)))
