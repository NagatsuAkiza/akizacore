from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from akizacore.cogs.ai.memory import MemoryCog
from akizacore.core.exceptions import PermissionDenied

GUILD = SimpleNamespace(id=10)
USER = SimpleNamespace(id=20)


def make_cog() -> tuple[MemoryCog, SimpleNamespace, SimpleNamespace]:
    service = SimpleNamespace(
        save=AsyncMock(),
        list=AsyncMock(return_value=[]),
        delete=AsyncMock(),
        clear=AsyncMock(return_value=0),
    )
    bot = SimpleNamespace(services=SimpleNamespace(memory=service))
    return MemoryCog(bot), service, bot


def make_interaction() -> SimpleNamespace:
    return SimpleNamespace(
        guild=GUILD,
        user=USER,
        response=SimpleNamespace(send_message=AsyncMock()),
    )


async def invoke(cog: MemoryCog, name: str, interaction: SimpleNamespace, *args: object) -> None:
    command = getattr(cog, name)
    await command.callback(cog, interaction, *args)


@pytest.mark.asyncio
async def test_save_passes_scope_and_content() -> None:
    cog, service, _ = make_cog()
    interaction = make_interaction()

    await invoke(cog, "save", interaction, "  Saya suka jawaban singkat.  ")

    service.save.assert_awaited_once_with(GUILD.id, USER.id, "  Saya suka jawaban singkat.  ")
    interaction.response.send_message.assert_awaited_once_with(
        "Memory berhasil disimpan.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_list_renders_ids_and_content() -> None:
    cog, service, _ = make_cog()
    service.list.return_value = [
        SimpleNamespace(id=7, content="Jawaban singkat."),
        SimpleNamespace(id=6, content="Bahasa Indonesia."),
    ]
    interaction = make_interaction()

    await invoke(cog, "list", interaction)

    interaction.response.send_message.assert_awaited_once_with(
        "7. Jawaban singkat.\n6. Bahasa Indonesia.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_list_reports_empty_and_truncates_long_output() -> None:
    cog, service, _ = make_cog()
    interaction = make_interaction()
    await invoke(cog, "list", interaction)
    assert interaction.response.send_message.call_args.args[0] == "Belum ada memory tersimpan."

    interaction.response.send_message.reset_mock()
    service.list.return_value = [SimpleNamespace(id=1, content="x" * 500)] * 20
    await invoke(cog, "list", interaction)
    assert len(interaction.response.send_message.call_args.args[0]) <= 1990


@pytest.mark.asyncio
async def test_delete_and_clear_report_success() -> None:
    cog, service, _ = make_cog()
    service.clear.return_value = 3
    interaction = make_interaction()

    await invoke(cog, "delete", interaction, 12)
    service.delete.assert_awaited_once_with(GUILD.id, USER.id, 12)
    assert interaction.response.send_message.call_args.args[0] == "Memory berhasil dihapus."

    interaction.response.send_message.reset_mock()
    await invoke(cog, "clear", interaction)
    service.clear.assert_awaited_once_with(GUILD.id, USER.id)
    interaction.response.send_message.assert_awaited_once_with(
        "3 memory berhasil dihapus.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_domain_error_does_not_claim_success() -> None:
    cog, service, _ = make_cog()
    service.save.side_effect = PermissionDenied(
        "Memory AI tidak tersedia karena kamu menonaktifkan fitur AI."
    )
    interaction = make_interaction()

    await invoke(cog, "save", interaction, "private")

    interaction.response.send_message.assert_awaited_once_with(
        "Memory AI tidak tersedia karena kamu menonaktifkan fitur AI.", ephemeral=True
    )
