from typing import cast

import discord
import structlog
from discord import app_commands
from discord.ext import commands

from akizacore.ai.context import ReplyContext
from akizacore.ai.orchestrator import AIOrchestrator, AskRequest, AskResult, TranslateRequest
from akizacore.ai.tools.base import ModerationGateway
from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import AkizaError
from akizacore.services.moderation import ModerationService
from akizacore.utils.converters import to_guild_info, to_user_info
from akizacore.utils.text import chunk_text

log = structlog.get_logger()


def _is_admin(user: discord.User | discord.Member) -> bool:
    """Snapshot izin Manage Server; menentukan apakah tool khusus admin boleh dipakai."""
    return isinstance(user, discord.Member) and user.guild_permissions.manage_guild


class _DiscordModerationGateway(ModerationGateway):
    def __init__(
        self,
        *,
        guild: discord.Guild,
        actor: discord.User | discord.Member,
        service: ModerationService,
    ) -> None:
        self.guild = guild
        self.actor = actor
        self.service = service

    async def _member(self, user_id: int) -> discord.Member:
        member = self.guild.get_member(user_id)
        if member is None:
            try:
                member = await self.guild.fetch_member(user_id)
            except discord.NotFound as exc:
                raise AkizaError("Member target tidak ditemukan di server ini.") from exc
            except discord.Forbidden as exc:
                raise AkizaError("Bot tidak bisa membaca member target.") from exc
        if member.bot:
            raise AkizaError("Bot tidak bisa menjadi target moderasi.")
        if member.id == self.guild.owner_id:
            raise AkizaError("Tidak bisa memoderasi owner server.")
        if member.id == self.actor.id:
            raise AkizaError("Tidak bisa memoderasi diri sendiri.")
        if self.guild.me is not None and member.top_role >= self.guild.me.top_role:
            raise AkizaError("Role target lebih tinggi dari role bot.")
        if (
            isinstance(self.actor, discord.Member)
            and self.actor.id != self.guild.owner_id
            and member.top_role >= self.actor.top_role
        ):
            raise AkizaError("Role target sama atau lebih tinggi dari kamu.")
        return member

    async def warn(self, target_id: int, reason: str) -> str:
        member = await self._member(target_id)
        result = await self.service.warn(
            server_id=self.guild.id,
            user_id=member.id,
            mod_id=self.actor.id,
            reason=reason,
        )
        return f"{member.display_name} diberi warning (total aktif: {result.total})."

    async def warnings(self, target_id: int) -> str:
        member = await self._member(target_id)
        items = await self.service.warnings(self.guild.id, member.id)
        if not items:
            return f"{member.display_name} tidak memiliki warning aktif."
        return "\n".join(f"#{item.id} oleh <@{item.mod_id}>: {item.reason}" for item in items)

    async def clear_warnings(self, target_id: int) -> str:
        member = await self._member(target_id)
        count = await self.service.clear_warnings(
            server_id=self.guild.id,
            user_id=member.id,
            mod_id=self.actor.id,
        )
        return f"{count} warning aktif milik {member.display_name} dihapus."

    async def modlog(self, target_id: int | None) -> str:
        if target_id is not None:
            await self._member(target_id)
        entries = await self.service.recent_logs(self.guild.id, limit=10, target_id=target_id)
        if not entries:
            return "Belum ada catatan moderasi."
        return "\n".join(
            f"#{entry.id} {entry.action} target <@{entry.target_id}>: {entry.reason}"
            for entry in entries
        )


class ChatCog(commands.Cog):
    """/ask, /translate, chat lewat mention, dan /forget. Lapisan tipis di atas AIOrchestrator."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    def _require_ai(self) -> AIOrchestrator:
        ai = self.bot.services.ai
        if ai is None:
            raise AkizaError("Fitur AI belum dikonfigurasi oleh pemilik bot.")
        return ai

    @staticmethod
    def _format(result: AskResult) -> list[str]:
        chunks = chunk_text(result.text) or ["(tidak ada jawaban)"]
        if result.coins_charged > 0:
            footer = f"-# {result.coins_charged} koin terpakai"
            if result.balance_after is not None:
                footer += f" \u00b7 saldo {result.balance_after}"
            chunks[-1] = f"{chunks[-1]}\n{footer}"
        return chunks

    async def _ask(
        self,
        *,
        guild: discord.Guild,
        channel_id: int,
        user: discord.User | discord.Member,
        prompt: str,
        reply_context: ReplyContext | None = None,
    ) -> list[str]:
        result = await self._require_ai().ask(
            AskRequest(
                server_id=guild.id,
                server_name=guild.name,
                channel_id=channel_id,
                user=to_user_info(user),
                prompt=prompt,
                is_admin=self.bot.is_owner_user(user.id) or _is_admin(user),
                reply_context=reply_context,
                moderation=_DiscordModerationGateway(
                    guild=guild,
                    actor=user,
                    service=self.bot.services.moderation,
                ),
            )
        )
        return self._format(result)

    @staticmethod
    async def _get_reply_context(message: discord.Message) -> ReplyContext | None:
        reference = message.reference
        if reference is None or reference.message_id is None:
            return None

        referenced = reference.resolved
        if not isinstance(referenced, discord.Message):
            try:
                referenced = await message.channel.fetch_message(reference.message_id)
            except discord.NotFound:
                return None
            except (discord.Forbidden, discord.HTTPException):
                log.warning(
                    "reply_context_unavailable",
                    channel_id=message.channel.id,
                    message_id=reference.message_id,
                )
                return None

        return ReplyContext(
            author_name=referenced.author.display_name,
            author_id=referenced.author.id,
            content=referenced.content,
            is_bot=referenced.author.bot,
        )

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

    @app_commands.command(name="translate", description="Terjemahkan teks dengan AI")
    @app_commands.describe(
        text="Teks yang diterjemahkan", target="Bahasa tujuan, mis. Inggris, Jepang, Sunda"
    )
    @app_commands.guild_only()
    async def translate(
        self,
        interaction: discord.Interaction,
        text: app_commands.Range[str, 1, 1500],
        target: app_commands.Range[str, 2, 30],
    ) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(thinking=True)
        result = await self._require_ai().translate(
            TranslateRequest(
                server_id=interaction.guild.id,
                user=to_user_info(interaction.user),
                text=text,
                target_language=target,
            )
        )
        for chunk in self._format(result):
            await interaction.followup.send(chunk)

    @app_commands.command(name="forget", description="Hapus riwayat percakapan AI-mu di server ini")
    @app_commands.guild_only()
    async def forget(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        ai = self._require_ai()
        count = await ai.forget(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            f"Riwayat percakapanmu dihapus ({count} percakapan). "
            f"Riwayat lainnya otomatis dihapus setelah {ai.retention_days} hari.",
            ephemeral=True,
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
            reply_context = await self._get_reply_context(message)
            async with message.channel.typing():
                await self.bot.services.onboarding.ensure_context(
                    to_user_info(message.author), to_guild_info(message.guild)
                )
                chunks = await self._ask(
                    guild=message.guild,
                    channel_id=message.channel.id,
                    user=message.author,
                    prompt=prompt,
                    reply_context=reply_context,
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
