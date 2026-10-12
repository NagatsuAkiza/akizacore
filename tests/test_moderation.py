from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]


async def test_warn_escalates_at_threshold(session_factory: Factory) -> None:
    mod = Services.build(session_factory).moderation
    first = await mod.warn(server_id=101, user_id=2, mod_id=3, reason="a")
    assert (first.total, first.escalate) == (1, False)
    await mod.warn(server_id=101, user_id=2, mod_id=3, reason="b")
    third = await mod.warn(server_id=101, user_id=2, mod_id=3, reason="c")
    assert (third.total, third.escalate) == (3, True)


async def test_warnings_list_and_clear(session_factory: Factory) -> None:
    mod = Services.build(session_factory).moderation
    await mod.warn(server_id=102, user_id=2, mod_id=3, reason="pertama")
    await mod.warn(server_id=102, user_id=2, mod_id=3, reason="kedua")

    items = await mod.warnings(102, 2)
    assert [w.reason for w in items] == ["kedua", "pertama"]
    assert items[0].created_at.tzinfo is not None
    assert items[0].created_at <= datetime.now(UTC)

    assert await mod.clear_warnings(server_id=102, user_id=2, mod_id=3) == 2
    assert await mod.warnings(102, 2) == []
    again = await mod.warn(server_id=102, user_id=2, mod_id=3, reason="baru")
    assert again.total == 1


async def test_actions_are_logged(session_factory: Factory) -> None:
    mod = Services.build(session_factory).moderation
    await mod.warn(server_id=103, user_id=2, mod_id=3, reason="spam")
    await mod.log_action(
        server_id=103, target_id=2, mod_id=None, action="automod:delete", reason="link"
    )

    logs = await mod.recent_logs(103)
    assert [(entry.action, entry.mod_id) for entry in logs] == [
        ("automod:delete", None),
        ("warn", 3),
    ]
    assert await mod.recent_logs(103, target_id=999) == []


async def test_automod_defaults_and_persistence(session_factory: Factory) -> None:
    mod = Services.build(session_factory).moderation
    view = await mod.get_automod(201)
    assert (view.anti_spam, view.anti_link, view.action) == (False, False, "delete")

    await mod.set_automod(
        201, anti_link=True, allowed_domains="Example.org, youtu.be", action="warn"
    )
    view = await mod.get_automod(201)
    assert view.anti_link is True
    assert view.allowed_domains == ("example.org", "youtu.be")
    assert view.action == "warn"


async def test_automod_rejects_bad_input(session_factory: Factory) -> None:
    mod = Services.build(session_factory).moderation
    with pytest.raises(ValueError):
        await mod.set_automod(202, action="ban")
    with pytest.raises(ValueError):
        await mod.set_automod(202, nonsense=True)
