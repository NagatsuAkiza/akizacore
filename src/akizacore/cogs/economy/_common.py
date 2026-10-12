import discord

from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import ValidationFailed
from akizacore.utils.converters import to_user_info

PARTY = "\U0001f389"


async def require_economy(bot: AkizaBot, interaction: discord.Interaction) -> int:
    """Pastikan command dipakai di server dan modul economy aktif. Return guild_id."""
    assert interaction.guild is not None
    await bot.services.settings.require_feature(interaction.guild.id, "economy")
    return interaction.guild.id


async def ensure_human(bot: AkizaBot, member: discord.Member) -> None:
    """Pastikan member lain terdaftar di database (FK) dan bukan bot."""
    if member.bot:
        raise ValidationFailed("Bot tidak punya akun ekonomi.")
    await bot.services.onboarding.ensure_user(to_user_info(member))


def level_note(leveled_up: bool, level: int, bonus: int) -> str:
    if not leveled_up:
        return ""
    return f"\n{PARTY} Naik ke **level {level}**! Bonus {bonus} koin."
