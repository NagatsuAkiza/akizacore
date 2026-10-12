from typing import cast

import discord
import structlog
from discord import app_commands
from discord.ext import commands

from akizacore.ai.orchestrator import AIOrchestrator, AskRequest
from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import AkizaError
from akizacore.utils.converters import to_guild_info, to_user_info
from akizacore.utils.text import chunk_text

log = structlog.get_logger()


class ChatCog(commands.Cog):
    """/ask, chat lewat mention, dan /forget. Lapisan tipis di atas AIOrchestrator."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    def _require_ai(self) -> AIOrchestrator:
        ai = self.bot.services.ai
        if ai is None:
            raise AkizaError("Fitur AI belum dikonfigurasi oleh pemilik bot.")
        return ai

    async def _ask(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        user: discord.User | discord.Member,
        prompt: str,
    ) -> list[str]:
        ai = self._require_ai()
        result = await ai.ask(
            AskRequest(
                server_id=guild.id,
                server_name=guild.name,
                channel_id=channel_id,
                user=to_user_info(user),
                prompt=prompt,
            )
        )
        chunks = chunk_text(result.text) or ["(tidak ada jawaban)"]
        if result.coins_charged > 0:
            footer = f"-# {result.coins_charged} koin terpakai"
            if result.balance_after is not None:
                footer += f" \u00b7 saldo {result.balance_after}"
            chunks[-1] = f"{chunks[-1]}\n{footer}"
        return chunks

    @app_commands.command(name="ask", description="Tanya apa saja ke AI")
    @app_commands.describe(prompt="Pertanyaan atau permintaanmu")
    @app_commands.guild_only()
    async def ask(
        self, interaction: discord.Interaction, prompt: app_commands.Range[str, 1, 1500]
    ) -> None:
        assert interaction.guild is not None and interaction.channel_id is not None
        await interaction.response.defer(thinking=True)
        chunks = await self._ask(
            guild=interaction.guild,
            channel_id=interaction.channel_id,
            user=interaction.user,
            prompt=prompt,
        )
        for chunk in chunks:
            await interaction.followup.send(chunk)

    @app_commands.command(name="forget", description="Hapus riwayat percakapan AI-mu di server ini")
    @app_commands.guild_only()
    async def forget(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        count = await self._require_ai().forget(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"Riwayat percakapanmu dihapus ({count} percakapan).", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        me = self.bot.user
        if message.author.bot or message.guild is None or me is None:
            return
        if me not in message.mentions:
            return
        prompt = message.content.replace(f"<@{me.id}>", "").replace(f"<@!{me.id}>", "").strip()
        if not prompt:
            return
        try:
            async with message.channel.typing():
                await self.bot.services.onboarding.ensure_context(
                    to_user_info(message.author), to_guild_info(message.guild)
                )
                chunks = await self._ask(
                    guild=message.guild,
                    channel_id=message.channel.id,
                    user=message.author,
                    prompt=prompt,
                )
        except AkizaError as exc:
            await message.reply(exc.user_message, mention_author=False)
            return
        except Exception:
            log.exception("mention_chat_error", guild_id=message.guild.id)
            await message.reply("Terjadi kesalahan internal.", mention_author=False)
            return
        for chunk in chunks:
            await message.reply(chunk, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChatCog(cast(AkizaBot, bot)))
