from datetime import timedelta
from typing import Literal, cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot
from akizacore.core.exceptions import AkizaError
from akizacore.services.moderation import ModerationService

NO_REASON = "Tanpa alasan"
NO_PING = discord.AllowedMentions.none()
BOT_FORBIDDEN = "Bot tidak punya izin untuk itu, atau role-nya lebih rendah dari target."


def _require(interaction: discord.Interaction, *perms: str) -> None:
    """Cek izin pemakai (sudah termasuk overwrite channel). Administrator otomatis lolos."""
    client = cast(AkizaBot, interaction.client)
    if client.is_owner_user(interaction.user.id):
        return
    resolved = interaction.permissions
    if not all(getattr(resolved, name, False) for name in perms):
        raise AkizaError("Kamu tidak punya izin untuk command ini.")


def _check_target(interaction: discord.Interaction, target: discord.Member) -> None:
    guild = interaction.guild
    actor = interaction.user
    assert guild is not None
    if target.id == actor.id:
        raise AkizaError("Tidak bisa dilakukan ke diri sendiri.")
    if guild.me is not None and target.id == guild.me.id:
        raise AkizaError("Tidak bisa dilakukan ke bot.")
    if target.id == guild.owner_id:
        raise AkizaError("Tidak bisa dilakukan ke owner server.")
    if (
        isinstance(actor, discord.Member)
        and actor.id != guild.owner_id
        and target.top_role >= actor.top_role
    ):
        raise AkizaError("Role target sama atau lebih tinggi dari kamu.")
    if guild.me is not None and target.top_role >= guild.me.top_role:
        raise AkizaError("Role target lebih tinggi dari role bot.")


class ModerationCog(commands.Cog):
    """Command moderasi. Aturan bisnis ada di ModerationService."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    @property
    def _svc(self) -> ModerationService:
        return self.bot.services.moderation

    @app_commands.command(name="warn", description="Beri peringatan ke member")
    @app_commands.describe(member="Member yang diperingatkan", reason="Alasan")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: app_commands.Range[str, 1, 300] = NO_REASON,
    ) -> None:
        assert interaction.guild is not None
        _require(interaction, "moderate_members")
        if member.bot:
            raise AkizaError("Bot tidak bisa di-warn.")
        _check_target(interaction, member)
        result = await self._svc.warn(
            server_id=interaction.guild.id,
            user_id=member.id,
            mod_id=interaction.user.id,
            reason=reason,
        )
        cfg = self._svc.config
        text = (
            f"{member.mention} diperingatkan ({result.total}/{cfg.warn_timeout_at}). "
            f"Alasan: {reason}"
        )
        if result.escalate:
            try:
                await member.timeout(
                    timedelta(minutes=cfg.warn_timeout_minutes),
                    reason=f"Auto-timeout: {result.total} warn",
                )
                text += f"\nOtomatis di-timeout {cfg.warn_timeout_minutes} menit."
            except discord.HTTPException:
                text += "\n(Gagal auto-timeout: cek izin dan posisi role bot.)"
        await interaction.response.send_message(text, allowed_mentions=NO_PING)

    @app_commands.command(name="warnings", description="Lihat warn aktif seorang member")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        _require(interaction, "moderate_members")
        items = await self._svc.warnings(interaction.guild.id, member.id)
        if not items:
            await interaction.response.send_message(
                f"{member.display_name} bersih, belum ada warn aktif.", ephemeral=True
            )
            return
        lines = [
            f"`#{w.id}` {discord.utils.format_dt(w.created_at, 'd')} "
            f"oleh <@{w.mod_id}>: {w.reason[:80]}"
            for w in items
        ]
        await interaction.response.send_message(
            f"Warn aktif {member.mention} (maks 10 terbaru):\n" + "\n".join(lines),
            ephemeral=True,
            allowed_mentions=NO_PING,
        )

    @app_commands.command(name="clearwarns", description="Hapus semua warn aktif seorang member")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def clearwarns(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        _require(interaction, "manage_guild")
        count = await self._svc.clear_warnings(
            server_id=interaction.guild.id, user_id=member.id, mod_id=interaction.user.id
        )
        await interaction.response.send_message(
            f"{count} warn milik {member.mention} dihapus.", allowed_mentions=NO_PING
        )

    @app_commands.command(name="kick", description="Keluarkan member dari server")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: app_commands.Range[str, 1, 300] = NO_REASON,
    ) -> None:
        assert interaction.guild is not None
        _require(interaction, "kick_members")
        _check_target(interaction, member)
        try:
            await member.kick(reason=f"{interaction.user}: {reason}")
        except discord.Forbidden as exc:
            raise AkizaError(BOT_FORBIDDEN) from exc
        await self._svc.log_action(
            server_id=interaction.guild.id,
            target_id=member.id,
            mod_id=interaction.user.id,
            action="kick",
            reason=reason,
        )
        await interaction.response.send_message(
            f"{member} di-kick. Alasan: {reason}", allowed_mentions=NO_PING
        )

    @app_commands.command(name="ban", description="Ban member dari server")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: app_commands.Range[str, 1, 300] = NO_REASON,
    ) -> None:
        assert interaction.guild is not None
        _require(interaction, "ban_members")
        _check_target(interaction, member)
        try:
            await member.ban(reason=f"{interaction.user}: {reason}", delete_message_days=0)
        except discord.Forbidden as exc:
            raise AkizaError(BOT_FORBIDDEN) from exc
        await self._svc.log_action(
            server_id=interaction.guild.id,
            target_id=member.id,
            mod_id=interaction.user.id,
            action="ban",
            reason=reason,
        )
        await interaction.response.send_message(
            f"{member} di-ban. Alasan: {reason}", allowed_mentions=NO_PING
        )

    @app_commands.command(name="timeout", description="Bisukan member sementara")
    @app_commands.describe(minutes="Durasi dalam menit (1 sampai 40320)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: app_commands.Range[str, 1, 300] = NO_REASON,
    ) -> None:
        assert interaction.guild is not None
        _require(interaction, "moderate_members")
        _check_target(interaction, member)
        try:
            await member.timeout(timedelta(minutes=minutes), reason=f"{interaction.user}: {reason}")
        except discord.Forbidden as exc:
            raise AkizaError(BOT_FORBIDDEN) from exc
        await self._svc.log_action(
            server_id=interaction.guild.id,
            target_id=member.id,
            mod_id=interaction.user.id,
            action=f"timeout:{minutes}m",
            reason=reason,
        )
        await interaction.response.send_message(
            f"{member.mention} di-timeout {minutes} menit. Alasan: {reason}",
            allowed_mentions=NO_PING,
        )

    @app_commands.command(name="untimeout", description="Cabut timeout member")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild is not None
        _require(interaction, "moderate_members")
        _check_target(interaction, member)
        try:
            await member.timeout(None, reason=f"Dicabut oleh {interaction.user}")
        except discord.Forbidden as exc:
            raise AkizaError(BOT_FORBIDDEN) from exc
        await self._svc.log_action(
            server_id=interaction.guild.id,
            target_id=member.id,
            mod_id=interaction.user.id,
            action="untimeout",
            reason="-",
        )
        await interaction.response.send_message(
            f"Timeout {member.mention} dicabut.", allowed_mentions=NO_PING
        )

    @app_commands.command(name="purge", description="Hapus pesan terakhir di channel ini")
    @app_commands.describe(amount="Jumlah pesan (1 sampai 100)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def purge(
        self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]
    ) -> None:
        assert interaction.guild is not None
        _require(interaction, "manage_messages")
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            raise AkizaError("Channel ini tidak mendukung purge.")
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await channel.purge(limit=amount)
        except discord.Forbidden as exc:
            raise AkizaError("Bot butuh izin Manage Messages dan Read Message History.") from exc
        await self._svc.log_action(
            server_id=interaction.guild.id,
            target_id=interaction.user.id,
            mod_id=interaction.user.id,
            action=f"purge:{len(deleted)}",
            reason=f"#{channel.name}",
        )
        await interaction.followup.send(f"{len(deleted)} pesan dihapus.", ephemeral=True)

    @app_commands.command(name="modlog", description="Lihat 10 aksi moderasi terakhir")
    @app_commands.describe(member="Filter berdasarkan member (opsional)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def modlog(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        assert interaction.guild is not None
        _require(interaction, "moderate_members")
        entries = await self._svc.recent_logs(
            interaction.guild.id, limit=10, target_id=member.id if member else None
        )
        if not entries:
            await interaction.response.send_message("Belum ada catatan moderasi.", ephemeral=True)
            return
        lines = []
        for e in entries:
            who = f"<@{e.mod_id}>" if e.mod_id else "automod"
            lines.append(
                f"`#{e.id}` {discord.utils.format_dt(e.created_at, 'R')} {e.action} "
                f"<@{e.target_id}> oleh {who}: {e.reason[:60]}"
            )
        await interaction.response.send_message(
            "\n".join(lines), ephemeral=True, allowed_mentions=NO_PING
        )

    @app_commands.command(name="automod", description="Lihat atau ubah pengaturan automod")
    @app_commands.describe(
        anti_spam="Hapus pesan beruntun yang terlalu cepat",
        spam_messages="Jumlah pesan dalam 8 detik yang dianggap spam (3 sampai 20)",
        anti_link="Hapus pesan berisi link yang tidak diizinkan",
        allowed_domains="Domain yang diizinkan, pisahkan dengan koma (kosongkan = tidak ada)",
        action="Tindakan selain menghapus pesan: delete, warn, atau timeout",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def automod(
        self,
        interaction: discord.Interaction,
        anti_spam: bool | None = None,
        spam_messages: app_commands.Range[int, 3, 20] | None = None,
        anti_link: bool | None = None,
        allowed_domains: app_commands.Range[str, 0, 300] | None = None,
        action: Literal["delete", "warn", "timeout"] | None = None,
    ) -> None:
        assert interaction.guild is not None
        _require(interaction, "manage_guild")
        changes: dict[str, object] = {
            "anti_spam": anti_spam,
            "spam_messages": spam_messages,
            "anti_link": anti_link,
            "allowed_domains": allowed_domains,
            "action": action,
        }
        changes = {key: value for key, value in changes.items() if value is not None}
        if changes:
            view = await self._svc.set_automod(interaction.guild.id, **changes)
        else:
            view = await self._svc.get_automod(interaction.guild.id)
        domains = ", ".join(view.allowed_domains) or "(tidak ada)"
        await interaction.response.send_message(
            "Pengaturan automod:\n"
            f"- anti-spam: {'aktif' if view.anti_spam else 'mati'} "
            f"({view.spam_messages} pesan / {view.spam_window_s} detik)\n"
            f"- anti-link: {'aktif' if view.anti_link else 'mati'}, domain diizinkan: {domains}\n"
            f"- tindakan: {view.action}"
            + (f" ({view.timeout_minutes} menit)" if view.action == "timeout" else ""),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(cast(AkizaBot, bot)))
