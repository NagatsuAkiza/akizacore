"""Cek keamanan target pada command moderasi manual (hierarchy, diri sendiri, owner, bot)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from akizacore.cogs.moderation.commands import ModerationCog, _check_target
from akizacore.core.exceptions import AkizaError
from tests.test_moderation_gateway import (
    ACTOR_ID,
    GUILD_ID,
    OWNER_ID,
    TARGET_ID,
    FakeRole,
    make_member,
)


def make_interaction(*, actor_position: int = 30, bot_position: int = 50) -> Any:
    guild = MagicMock(spec=discord.Guild)
    guild.id = GUILD_ID
    guild.owner_id = OWNER_ID
    guild.me = SimpleNamespace(id=1, top_role=FakeRole(1, bot_position))
    interaction = MagicMock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = make_member(ACTOR_ID, actor_position)
    interaction.permissions = discord.Permissions(moderate_members=True)
    interaction.client = SimpleNamespace(is_owner_user=lambda _user_id: False)
    interaction.response = SimpleNamespace(send_message=AsyncMock())
    return interaction


def test_check_target_accepts_lower_role() -> None:
    _check_target(make_interaction(), make_member(TARGET_ID, 10))


@pytest.mark.parametrize(
    ("position", "message"),
    [(30, "sama atau lebih tinggi dari kamu"), (40, "sama atau lebih tinggi dari kamu")],
)
def test_check_target_rejects_equal_or_higher_than_actor(position: int, message: str) -> None:
    with pytest.raises(AkizaError, match=message):
        _check_target(make_interaction(), make_member(TARGET_ID, position))


def test_check_target_rejects_role_above_bot() -> None:
    interaction = make_interaction(actor_position=60, bot_position=50)
    with pytest.raises(AkizaError, match="lebih tinggi dari role bot"):
        _check_target(interaction, make_member(TARGET_ID, 55))


def test_check_target_rejects_self_and_server_owner() -> None:
    interaction = make_interaction()
    with pytest.raises(AkizaError, match="diri sendiri"):
        _check_target(interaction, make_member(ACTOR_ID, 10))
    with pytest.raises(AkizaError, match="owner server"):
        _check_target(interaction, make_member(OWNER_ID, 10))


def make_cog() -> tuple[ModerationCog, Any]:
    service = SimpleNamespace(log_action=AsyncMock())
    bot: Any = SimpleNamespace(services=SimpleNamespace(moderation=service))
    return ModerationCog(bot), service


async def test_untimeout_rejects_target_above_actor() -> None:
    cog, service = make_cog()
    interaction = make_interaction()
    target = make_member(TARGET_ID, 40)  # di atas actor (30)

    with pytest.raises(AkizaError, match="sama atau lebih tinggi dari kamu"):
        await cog.untimeout.callback(cog, interaction, target)

    target.timeout.assert_not_awaited()
    service.log_action.assert_not_awaited()


async def test_untimeout_works_for_lower_role_and_is_logged() -> None:
    cog, service = make_cog()
    interaction = make_interaction()
    target = make_member(TARGET_ID, 10)

    await cog.untimeout.callback(cog, interaction, target)

    target.timeout.assert_awaited_once()
    assert target.timeout.await_args.args == (None,)
    service.log_action.assert_awaited_once()
    assert service.log_action.await_args.kwargs["action"] == "untimeout"
