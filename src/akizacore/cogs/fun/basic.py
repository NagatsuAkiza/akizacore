from __future__ import annotations

import random
from dataclasses import dataclass
from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.core.bot import AkizaBot

JOKES = (
    ("Kenapa programmer suka kopi?", "Karena tanpa Java, hidupnya error."),
    ("Apa makanan favorit bot Discord?", "Byte-bite."),
    ("Kenapa database tidak pernah tersesat?", "Karena selalu punya index."),
)
REACTIONS = {
    "happy": "🎉",
    "love": "❤️",
    "laugh": "😂",
    "sad": "😢",
    "angry": "😤",
    "surprised": "😮",
}


def parse_poll_options(
    option_a: str,
    option_b: str,
    option_c: str | None = None,
    option_d: str | None = None,
    option_e: str | None = None,
) -> list[str]:
    options = [option_a, option_b, option_c, option_d, option_e]
    cleaned = [option.strip() for option in options if option and option.strip()]
    if len(cleaned) < 2:
        raise ValueError("Poll membutuhkan setidaknya dua pilihan.")
    if len({option.casefold() for option in cleaned}) != len(cleaned):
        raise ValueError("Pilihan poll tidak boleh duplikat.")
    return cleaned


@dataclass
class PollState:
    options: list[str]
    votes: dict[int, int]

    def vote(self, user_id: int, option_index: int) -> None:
        self.votes[user_id] = option_index

    def counts(self) -> list[int]:
        return [
            sum(index == option_index for index in self.votes.values())
            for option_index in range(len(self.options))
        ]


class PollButton(discord.ui.Button["PollView"]):
    def __init__(self, owner: PollView, option_index: int, label: str) -> None:
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"akiza-poll-{option_index}",
        )
        self.owner = owner
        self.option_index = option_index

    async def callback(self, interaction: discord.Interaction) -> None:
        self.owner.state.vote(interaction.user.id, self.option_index)
        counts = self.owner.state.counts()
        for index, child in enumerate(self.owner.children):
            if isinstance(child, discord.ui.Button):
                child.label = f"{self.owner.state.options[index][:70]} ({counts[index]})"
        await interaction.response.edit_message(view=self.owner)


class PollView(discord.ui.View):
    def __init__(self, options: list[str]) -> None:
        super().__init__(timeout=86_400)
        self.state = PollState(options, {})
        for index, option in enumerate(options):
            self.add_item(PollButton(self, index, option))


class FunCog(commands.Cog):
    """Fitur hiburan lokal yang tidak membutuhkan provider eksternal."""

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    async def _require_fun(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await self.bot.services.settings.require_feature(interaction.guild.id, "fun")

    @app_commands.command(name="joke", description="Dapatkan lelucon singkat")
    @app_commands.guild_only()
    async def joke(self, interaction: discord.Interaction) -> None:
        await self._require_fun(interaction)
        setup, punchline = random.choice(JOKES)
        await interaction.response.send_message(f"**{setup}**\n||{punchline}||")

    @app_commands.command(name="meme", description="Buat meme teks sederhana")
    @app_commands.describe(top="Teks bagian atas", bottom="Teks bagian bawah")
    @app_commands.guild_only()
    async def meme(
        self,
        interaction: discord.Interaction,
        top: app_commands.Range[str, 1, 80],
        bottom: app_commands.Range[str, 1, 80],
    ) -> None:
        await self._require_fun(interaction)
        embed = discord.Embed(
            title="Meme AkizaCore",
            description=f"**{top}**\n\n━━━━━━━━━━━━\n\n**{bottom}**",
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="react", description="Kirim reaction emoji")
    @app_commands.describe(kind="Jenis reaction")
    @app_commands.choices(
        kind=[app_commands.Choice(name=name.title(), value=name) for name in REACTIONS]
    )
    @app_commands.guild_only()
    async def react(self, interaction: discord.Interaction, kind: str) -> None:
        await self._require_fun(interaction)
        emoji = REACTIONS.get(kind)
        if emoji is None:
            await interaction.response.send_message(
                "Jenis reaction tidak tersedia.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"{interaction.user.mention} {emoji}")

    @app_commands.command(name="poll", description="Buat poll interaktif")
    @app_commands.describe(
        question="Pertanyaan poll",
        option_a="Pilihan pertama",
        option_b="Pilihan kedua",
        option_c="Pilihan ketiga (opsional)",
        option_d="Pilihan keempat (opsional)",
        option_e="Pilihan kelima (opsional)",
    )
    @app_commands.guild_only()
    async def poll(
        self,
        interaction: discord.Interaction,
        question: app_commands.Range[str, 1, 200],
        option_a: app_commands.Range[str, 1, 80],
        option_b: app_commands.Range[str, 1, 80],
        option_c: app_commands.Range[str, 1, 80] | None = None,
        option_d: app_commands.Range[str, 1, 80] | None = None,
        option_e: app_commands.Range[str, 1, 80] | None = None,
    ) -> None:
        await self._require_fun(interaction)
        try:
            options = parse_poll_options(option_a, option_b, option_c, option_d, option_e)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        view = PollView(options)
        embed = discord.Embed(
            title="📊 Poll",
            description=question,
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"Dibuat oleh {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(FunCog(cast(AkizaBot, bot)))
