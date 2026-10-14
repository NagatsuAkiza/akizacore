"""Warn dan hapus-warning lewat AI wajib /confirm, sama seperti aksi destruktif."""

import discord
import pytest

from akizacore.core.exceptions import AkizaError
from tests.test_moderation_gateway import (
    ACTOR_ID,
    GUILD_ID,
    MANAGE_GUILD_ONLY,
    TARGET_ID,
    FakeRole,
    build,
    confirm,
    logged_actions,
)


async def test_warn_is_pending_until_confirmed_with_exact_params() -> None:
    env = build()
    reply = await env.gateway.warn(TARGET_ID, "spam")

    assert "Konfirmasi diperlukan" in reply
    assert "warn" in reply and "spam" in reply and str(TARGET_ID) in reply
    env.service.warn.assert_not_awaited()

    await confirm(env, reply)
    env.service.warn.assert_awaited_once_with(
        server_id=GUILD_ID, user_id=TARGET_ID, mod_id=ACTOR_ID, reason="spam"
    )


async def test_clear_warnings_is_pending_until_confirmed_with_exact_params() -> None:
    env = build()
    reply = await env.gateway.clear_warnings(TARGET_ID)

    assert "Konfirmasi diperlukan" in reply
    env.service.clear_warnings.assert_not_awaited()

    await confirm(env, reply)
    env.service.clear_warnings.assert_awaited_once_with(
        server_id=GUILD_ID, user_id=TARGET_ID, mod_id=ACTOR_ID
    )


async def test_warn_token_is_single_use() -> None:
    env = build()
    reply = await env.gateway.warn(TARGET_ID, "spam")
    await confirm(env, reply)
    with pytest.raises(AkizaError, match="tidak valid"):
        await confirm(env, reply)
    env.service.warn.assert_awaited_once()


async def test_invalid_target_never_produces_a_token() -> None:
    env = build(target_position=40)  # target di atas actor (30)
    with pytest.raises(AkizaError, match="sama atau lebih tinggi dari kamu"):
        await env.gateway.warn(TARGET_ID, "spam")
    with pytest.raises(AkizaError, match="sama atau lebih tinggi dari kamu"):
        await env.gateway.clear_warnings(TARGET_ID)
    assert env.confirmations._pending == {}


async def test_permission_revoked_before_confirm_blocks_warn_and_logs_failure() -> None:
    env = build()
    reply = await env.gateway.warn(TARGET_ID, "spam")
    env.actor.guild_permissions = discord.Permissions.none()

    with pytest.raises(AkizaError, match="izin Discord"):
        await confirm(env, reply)

    env.service.warn.assert_not_awaited()
    assert logged_actions(env) == ["ai_warn_failed"]


async def test_hierarchy_change_before_confirm_blocks_clear_warnings() -> None:
    env = build(actor_perms=MANAGE_GUILD_ONLY)
    reply = await env.gateway.clear_warnings(TARGET_ID)
    env.target.top_role = FakeRole(
        77, 40
    )  # target dipromosikan di atas actor (30), di bawah bot (50)

    with pytest.raises(AkizaError, match="sama atau lebih tinggi dari kamu"):
        await confirm(env, reply)

    env.service.clear_warnings.assert_not_awaited()
    assert logged_actions(env) == ["ai_clear_warnings_failed"]


async def test_service_failure_after_confirm_is_logged_and_token_consumed() -> None:
    env = build()
    env.service.warn.side_effect = AkizaError("database down")
    reply = await env.gateway.warn(TARGET_ID, "spam")

    with pytest.raises(AkizaError, match="database down"):
        await confirm(env, reply)

    assert logged_actions(env) == ["ai_warn_failed"]
    with pytest.raises(AkizaError, match="tidak valid"):
        await confirm(env, reply)


async def test_bot_owner_skips_permission_but_still_needs_confirmation() -> None:
    env = build(actor_perms=discord.Permissions.none(), actor_is_owner=True)
    reply = await env.gateway.warn(TARGET_ID, "spam")

    assert "Konfirmasi diperlukan" in reply
    env.service.warn.assert_not_awaited()
