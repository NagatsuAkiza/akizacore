"""Test jalur AI untuk moderasi destruktif: token konfirmasi, izin, hierarchy, dan logging."""

import re
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from akizacore.ai.tools import ToolContext, ToolExecutor
from akizacore.ai.tools.builtin import build_default_registry
from akizacore.cogs.ai.chat import _ConfirmationManager, _DiscordModerationGateway
from akizacore.core.exceptions import AkizaError
from akizacore.schemas.discord import UserInfo

GUILD_ID = 1
OWNER_ID = 999
ACTOR_ID = 20
TARGET_ID = 30
ROLE_ID = 40

ALL_PERMS = discord.Permissions(
    kick_members=True,
    ban_members=True,
    moderate_members=True,
    manage_messages=True,
    manage_roles=True,
    manage_guild=True,
)
MANAGE_GUILD_ONLY = discord.Permissions(manage_guild=True)

# action -> (izin Discord yang dibutuhkan, argumen tambahan request)
ACTIONS: dict[str, tuple[str, dict[str, Any]]] = {
    "kick": ("kick_members", {}),
    "ban": ("ban_members", {}),
    "timeout": ("moderate_members", {"minutes": 15}),
    "untimeout": ("moderate_members", {}),
    "purge": ("manage_messages", {"amount": 3}),
    "add_role": ("manage_roles", {"role_id": ROLE_ID}),
    "remove_role": ("manage_roles", {"role_id": ROLE_ID}),
}


class FakeRole:
    """Role palsu dengan perbandingan posisi seperti discord.Role."""

    def __init__(
        self, role_id: int, position: int, *, managed: bool = False, default: bool = False
    ) -> None:
        self.id = role_id
        self.position = position
        self.managed = managed
        self.name = f"role-{role_id}"
        self._default = default

    def is_default(self) -> bool:
        return self._default

    def __ge__(self, other: "FakeRole") -> bool:
        return self.position >= other.position


def http_error(cls: type[discord.HTTPException], status: int) -> discord.HTTPException:
    return cls(SimpleNamespace(status=status, reason="x"), "x")  # type: ignore[arg-type]


def make_member(member_id: int, position: int, perms: discord.Permissions | None = None) -> Any:
    member = MagicMock(spec=discord.Member)
    member.id = member_id
    member.bot = False
    member.display_name = f"user{member_id}"
    member.top_role = FakeRole(1000 + member_id, position)
    member.guild_permissions = perms or discord.Permissions.none()
    for method in ("kick", "ban", "timeout", "add_roles", "remove_roles"):
        setattr(member, method, AsyncMock())
    return member


@dataclass
class Env:
    gateway: _DiscordModerationGateway
    confirmations: _ConfirmationManager
    guild: Any
    actor: Any
    target: Any
    channel: Any
    role: FakeRole
    service: Any


def build(
    *,
    actor_perms: discord.Permissions = ALL_PERMS,
    actor_is_owner: bool = False,
    actor_position: int = 30,
    target_position: int = 10,
    bot_position: int = 50,
    role_position: int = 5,
) -> Env:
    actor = make_member(ACTOR_ID, actor_position, actor_perms)
    target = make_member(TARGET_ID, target_position)
    role = FakeRole(ROLE_ID, role_position)
    members = {ACTOR_ID: actor, TARGET_ID: target}

    guild = MagicMock(spec=discord.Guild)
    guild.id = GUILD_ID
    guild.owner_id = OWNER_ID
    guild.me = SimpleNamespace(id=1, top_role=FakeRole(1, bot_position))
    guild.get_member = MagicMock(side_effect=members.get)
    guild.fetch_member = AsyncMock(side_effect=http_error(discord.NotFound, 404))
    guild.get_role = MagicMock(side_effect=lambda rid: role if rid == ROLE_ID else None)

    channel = MagicMock(spec=discord.TextChannel)
    channel.name = "general"
    channel.purge = AsyncMock(return_value=[object(), object(), object()])
    channel.permissions_for = MagicMock(side_effect=lambda member: member.guild_permissions)

    service = SimpleNamespace(
        log_action=AsyncMock(),
        warn=AsyncMock(return_value=SimpleNamespace(total=1)),
        warnings=AsyncMock(return_value=[]),
        clear_warnings=AsyncMock(return_value=0),
        recent_logs=AsyncMock(return_value=[]),
    )
    confirmations = _ConfirmationManager()
    gateway = _DiscordModerationGateway(
        guild=guild,
        actor=actor,
        service=service,  # type: ignore[arg-type]
        confirmations=confirmations,
        channel=channel,
        actor_is_owner=actor_is_owner,
    )
    return Env(gateway, confirmations, guild, actor, target, channel, role, service)


async def request(env: Env, action: str, **override: Any) -> str:
    kwargs: dict[str, Any] = {
        "action": action,
        "target_id": None if action == "purge" else TARGET_ID,
        "reason": "spam",
        **ACTIONS[action][1],
    }
    kwargs.update(override)
    return await env.gateway.request_destructive(**kwargs)


async def confirm(env: Env, reply: str) -> str:
    match = re.search(r"token:([\w-]+)", reply)
    assert match is not None, reply
    return await env.confirmations.consume(
        token=match.group(1), guild_id=GUILD_ID, actor_id=ACTOR_ID
    )


def logged_actions(env: Env) -> list[str]:
    return [call.kwargs["action"] for call in env.service.log_action.await_args_list]


def assert_executed(env: Env, action: str) -> None:
    target = env.target
    if action == "kick":
        target.kick.assert_awaited_once_with(reason="spam")
    elif action == "ban":
        target.ban.assert_awaited_once_with(reason="spam", delete_message_days=0)
    elif action == "timeout":
        target.timeout.assert_awaited_once_with(timedelta(minutes=15), reason="spam")
    elif action == "untimeout":
        target.timeout.assert_awaited_once_with(None, reason="spam")
    elif action == "purge":
        env.channel.purge.assert_awaited_once_with(limit=3)
    elif action == "add_role":
        target.add_roles.assert_awaited_once_with(env.role, reason="spam")
    else:
        target.remove_roles.assert_awaited_once_with(env.role, reason="spam")


def assert_nothing_executed(env: Env) -> None:
    for method in ("kick", "ban", "timeout", "add_roles", "remove_roles"):
        getattr(env.target, method).assert_not_awaited()
    env.channel.purge.assert_not_awaited()


# ---------- Setiap aksi: tertunda sampai dikonfirmasi, lalu persis sesuai parameter ----------
@pytest.mark.parametrize("action", list(ACTIONS))
async def test_action_runs_only_after_confirmation_with_exact_params(action: str) -> None:
    env = build()
    reply = await request(env, action)

    assert_nothing_executed(env)
    env.service.log_action.assert_not_awaited()

    result = await confirm(env, reply)

    assert_executed(env, action)
    expected_log = "ai_purge:3" if action == "purge" else f"ai_{action}"
    assert logged_actions(env) == [expected_log]
    assert result


async def test_token_is_single_use() -> None:
    env = build()
    reply = await request(env, "kick")
    await confirm(env, reply)
    with pytest.raises(AkizaError, match="tidak valid"):
        await confirm(env, reply)
    env.target.kick.assert_awaited_once()


async def test_reply_summarizes_target_reason_and_params() -> None:
    env = build()
    timeout_reply = await request(env, "timeout", reason="spam\nlink")
    assert f"({TARGET_ID})" in timeout_reply
    assert "15 menit" in timeout_reply
    assert "alasan: spam link" in timeout_reply  # newline dirapikan

    role_reply = await request(env, "add_role")
    assert f"({ROLE_ID})" in role_reply

    purge_reply = await request(env, "purge")
    assert "3 pesan" in purge_reply


async def test_summary_is_stored_with_pending_confirmation() -> None:
    env = build()
    reply = await request(env, "ban")
    token = re.search(r"token:([\w-]+)", reply)
    assert token is not None
    pending = env.confirmations._pending[token.group(1)]
    assert pending.summary.startswith("ban, target user30")


# ---------- Izin Discord spesifik, bukan hanya Manage Server ----------
@pytest.mark.parametrize("action", list(ACTIONS))
async def test_manage_guild_alone_cannot_request_destructive_action(action: str) -> None:
    env = build(actor_perms=MANAGE_GUILD_ONLY)
    with pytest.raises(AkizaError, match="izin Discord"):
        await request(env, action)
    assert env.confirmations._pending == {}
    assert_nothing_executed(env)


@pytest.mark.parametrize("action", list(ACTIONS))
async def test_exact_permission_is_enough(action: str) -> None:
    permission = ACTIONS[action][0]
    env = build(actor_perms=discord.Permissions(**{permission: True}))
    await request(env, action)
    assert len(env.confirmations._pending) == 1


async def test_bot_owner_bypasses_permission_but_not_target_safety() -> None:
    env = build(actor_perms=discord.Permissions.none(), actor_is_owner=True)
    reply = await request(env, "kick")
    await confirm(env, reply)
    env.target.kick.assert_awaited_once()

    env.target.top_role = FakeRole(77, 60)  # di atas role bot
    with pytest.raises(AkizaError, match="role bot"):
        await request(env, "kick")


async def test_permission_revoked_before_confirmation_blocks_and_logs_failure() -> None:
    env = build()
    reply = await request(env, "kick")
    env.actor.guild_permissions = discord.Permissions.none()

    with pytest.raises(AkizaError, match="izin Discord"):
        await confirm(env, reply)

    env.target.kick.assert_not_awaited()
    assert logged_actions(env) == ["ai_kick_failed"]


async def test_purge_uses_channel_permissions() -> None:
    env = build()
    env.channel.permissions_for = MagicMock(return_value=discord.Permissions.none())
    with pytest.raises(AkizaError, match="izin Discord"):
        await request(env, "purge")


# ---------- Target safety dan role hierarchy di jalur AI ----------
@pytest.mark.parametrize(
    "action", ["kick", "ban", "timeout", "untimeout", "add_role", "remove_role"]
)
async def test_target_higher_than_actor_is_rejected(action: str) -> None:
    env = build(target_position=40)
    with pytest.raises(AkizaError, match="sama atau lebih tinggi dari kamu"):
        await request(env, action)


async def test_target_equal_to_actor_role_is_rejected() -> None:
    env = build(target_position=30)
    with pytest.raises(AkizaError, match="sama atau lebih tinggi"):
        await request(env, "kick")


async def test_target_higher_than_bot_is_rejected() -> None:
    env = build(actor_position=90, target_position=60)
    with pytest.raises(AkizaError, match="role bot"):
        await request(env, "ban")


async def test_bot_target_is_rejected() -> None:
    env = build()
    env.target.bot = True
    with pytest.raises(AkizaError, match="Bot tidak bisa"):
        await request(env, "kick")


async def test_server_owner_target_is_rejected() -> None:
    env = build()
    env.target.id = OWNER_ID
    env.guild.get_member = MagicMock(side_effect={ACTOR_ID: env.actor, OWNER_ID: env.target}.get)
    with pytest.raises(AkizaError, match="owner server"):
        await request(env, "ban", target_id=OWNER_ID)


async def test_self_target_is_rejected() -> None:
    env = build()
    with pytest.raises(AkizaError, match="diri sendiri"):
        await request(env, "timeout", target_id=ACTOR_ID)


async def test_unknown_target_is_rejected() -> None:
    env = build()
    with pytest.raises(AkizaError, match="tidak ditemukan"):
        await request(env, "kick", target_id=12345)


async def test_hierarchy_change_after_request_is_revalidated_on_confirm() -> None:
    env = build()
    reply = await request(env, "kick")
    env.target.top_role = FakeRole(77, 40)  # target dipromosikan di atas actor

    with pytest.raises(AkizaError, match="sama atau lebih tinggi dari kamu"):
        await confirm(env, reply)

    env.target.kick.assert_not_awaited()
    assert logged_actions(env) == ["ai_kick_failed"]


# ---------- Validasi role ----------
@pytest.mark.parametrize("action", ["add_role", "remove_role"])
async def test_role_must_be_below_actor_and_bot(action: str) -> None:
    env = build(role_position=30)  # sama dengan actor
    with pytest.raises(AkizaError, match="role tertinggi kamu"):
        await request(env, action)

    env = build(actor_position=90, role_position=50)  # sama dengan bot
    with pytest.raises(AkizaError, match="role bot"):
        await request(env, action)


async def test_managed_and_default_roles_are_rejected() -> None:
    env = build()
    env.role.managed = True
    with pytest.raises(AkizaError, match="tidak bisa dikelola"):
        await request(env, "add_role")

    env = build()
    env.role._default = True
    with pytest.raises(AkizaError, match="tidak bisa dikelola"):
        await request(env, "add_role")


async def test_unknown_role_is_rejected() -> None:
    env = build()
    with pytest.raises(AkizaError, match="Role tidak ditemukan"):
        await request(env, "add_role", role_id=424242)


async def test_guild_owner_actor_skips_actor_hierarchy_only() -> None:
    env = build(target_position=40, role_position=40)
    env.actor.id = OWNER_ID
    env.guild.get_member = MagicMock(side_effect={OWNER_ID: env.actor, TARGET_ID: env.target}.get)
    env.gateway.actor = env.actor
    await request(env, "kick")
    await request(env, "add_role")

    env.target.top_role = FakeRole(77, 60)  # di atas bot: tetap ditolak
    with pytest.raises(AkizaError, match="role bot"):
        await request(env, "kick")


# ---------- Parameter wajib ----------
@pytest.mark.parametrize(
    ("action", "override", "message"),
    [
        ("kick", {"target_id": None}, "user_id target"),
        ("timeout", {"minutes": None}, "minutes"),
        ("purge", {"amount": None}, "amount"),
        ("add_role", {"role_id": None}, "role_id"),
        ("remove_role", {"role_id": None}, "role_id"),
    ],
)
async def test_missing_required_params_are_rejected(
    action: str, override: dict[str, Any], message: str
) -> None:
    env = build()
    with pytest.raises(AkizaError, match=message):
        await request(env, action, **override)
    assert env.confirmations._pending == {}


async def test_unknown_action_is_rejected() -> None:
    env = build()
    with pytest.raises(AkizaError, match="tidak dikenal"):
        await env.gateway.request_destructive(action="nuke", target_id=TARGET_ID, reason="x")


async def test_purge_in_unsupported_channel_is_rejected() -> None:
    env = build()
    env.gateway.channel = MagicMock(spec=discord.abc.Messageable)
    with pytest.raises(AkizaError, match="tidak mendukung purge"):
        await request(env, "purge")


# ---------- Kegagalan dicatat ke moderation log ----------
@pytest.mark.parametrize("exc_cls", [discord.Forbidden, discord.HTTPException])
@pytest.mark.parametrize(
    ("action", "method"),
    [
        ("kick", "kick"),
        ("ban", "ban"),
        ("timeout", "timeout"),
        ("untimeout", "timeout"),
        ("add_role", "add_roles"),
        ("remove_role", "remove_roles"),
    ],
)
async def test_discord_failure_is_logged_and_token_is_consumed(
    action: str, method: str, exc_cls: type[discord.HTTPException]
) -> None:
    env = build()
    getattr(env.target, method).side_effect = http_error(exc_cls, 403)
    reply = await request(env, action)

    with pytest.raises(AkizaError):
        await confirm(env, reply)

    assert logged_actions(env) == [f"ai_{action}_failed"]
    with pytest.raises(AkizaError, match="tidak valid"):
        await confirm(env, reply)


@pytest.mark.parametrize("exc_cls", [discord.Forbidden, discord.HTTPException])
async def test_purge_failure_is_logged(exc_cls: type[discord.HTTPException]) -> None:
    env = build()
    env.channel.purge.side_effect = http_error(exc_cls, 403)
    reply = await request(env, "purge")

    with pytest.raises(AkizaError):
        await confirm(env, reply)

    assert logged_actions(env) == ["ai_purge_failed"]
    # target log untuk purge adalah actor, sama dengan command manual
    assert env.service.log_action.await_args.kwargs["target_id"] == ACTOR_ID


async def test_failure_log_error_does_not_mask_original_error() -> None:
    env = build()
    env.target.kick.side_effect = http_error(discord.Forbidden, 403)
    env.service.log_action.side_effect = RuntimeError("db down")
    reply = await request(env, "kick")

    with pytest.raises(AkizaError, match="hierarchy"):
        await confirm(env, reply)


async def test_failed_action_does_not_log_success() -> None:
    env = build()
    env.target.ban.side_effect = http_error(discord.Forbidden, 403)
    reply = await request(env, "ban")
    with pytest.raises(AkizaError):
        await confirm(env, reply)
    assert "ai_ban" not in logged_actions(env)


# ---------- Tool non-destruktif ikut memakai izin spesifik ----------
async def test_warn_requires_moderate_members() -> None:
    env = build(actor_perms=MANAGE_GUILD_ONLY)
    with pytest.raises(AkizaError, match="izin Discord"):
        await env.gateway.warn(TARGET_ID, "spam")
    with pytest.raises(AkizaError, match="izin Discord"):
        await env.gateway.warnings(TARGET_ID)
    with pytest.raises(AkizaError, match="izin Discord"):
        await env.gateway.modlog(None)
    env.service.warn.assert_not_awaited()


async def test_warn_allowed_with_moderate_members() -> None:
    env = build(actor_perms=discord.Permissions(moderate_members=True))
    assert "diberi warning" in await env.gateway.warn(TARGET_ID, "spam")
    with pytest.raises(AkizaError, match="izin Discord"):
        await env.gateway.clear_warnings(TARGET_ID)  # butuh manage_guild, sama seperti /clearwarns


async def test_clear_warnings_allowed_with_manage_guild() -> None:
    env = build(actor_perms=MANAGE_GUILD_ONLY)
    assert "dihapus" in await env.gateway.clear_warnings(TARGET_ID)


# ---------- Registry: tool hanya muncul bila admin, modul aktif, dan gateway tersedia ----------
MODERATION_TOOLS = {
    "moderation_warn",
    "moderation_warnings",
    "moderation_clear_warnings",
    "moderation_modlog",
    "moderation_request",
}
USER = UserInfo(id=ACTOR_ID, username="admin")


def tool_context(*, admin: bool, feature: bool, gateway: bool) -> ToolContext:
    return ToolContext(
        server_id=GUILD_ID,
        user=USER,
        is_admin=admin,
        features={"moderation": feature},
        moderation=AsyncMock() if gateway else None,
    )


def offered_moderation_tools(ctx: ToolContext) -> set[str]:
    registry = build_default_registry(economy=AsyncMock(), shop=AsyncMock(), stats=AsyncMock())
    return {spec.name for spec in registry.specs_for(ctx)} & MODERATION_TOOLS


@pytest.mark.parametrize(
    ("admin", "feature", "gateway"),
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
        (False, False, False),
    ],
)
def test_moderation_tools_hidden_unless_all_conditions_hold(
    admin: bool, feature: bool, gateway: bool
) -> None:
    assert (
        offered_moderation_tools(tool_context(admin=admin, feature=feature, gateway=gateway))
        == set()
    )


def test_moderation_tools_offered_when_admin_feature_and_gateway_present() -> None:
    ctx = tool_context(admin=True, feature=True, gateway=True)
    assert offered_moderation_tools(ctx) == MODERATION_TOOLS


async def test_executor_refuses_moderation_tool_without_gateway() -> None:
    registry = build_default_registry(economy=AsyncMock(), shop=AsyncMock(), stats=AsyncMock())
    executor = ToolExecutor(registry)
    ctx = tool_context(admin=True, feature=True, gateway=False)
    result = await executor.run_named("moderation_request", '{"action": "kick", "user_id": 5}', ctx)
    assert result.startswith("Ditolak")


async def test_executor_refuses_moderation_request_for_non_admin() -> None:
    registry = build_default_registry(economy=AsyncMock(), shop=AsyncMock(), stats=AsyncMock())
    executor = ToolExecutor(registry)
    ctx = tool_context(admin=False, feature=True, gateway=True)
    result = await executor.run_named("moderation_request", '{"action": "kick", "user_id": 5}', ctx)
    assert result.startswith("Ditolak")
    ctx.moderation.request_destructive.assert_not_awaited()  # type: ignore[union-attr]
