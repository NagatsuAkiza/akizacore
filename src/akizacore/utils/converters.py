import discord

from akizacore.schemas.discord import GuildInfo, UserInfo


def to_user_info(user: discord.User | discord.Member) -> UserInfo:
    return UserInfo(id=user.id, username=user.name, avatar=user.avatar.key if user.avatar else None)


def to_guild_info(guild: discord.Guild) -> GuildInfo:
    return GuildInfo(id=guild.id, name=guild.name, owner_id=guild.owner_id)
