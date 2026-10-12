from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

from akizacore.cogs.economy._common import require_economy
from akizacore.core.bot import AkizaBot


class ShopCog(commands.Cog):
    """Toko, pembelian, dan inventory. Admin mengelola item lewat /shopadmin."""

    shopadmin_group = app_commands.Group(
        name="shopadmin",
        description="Kelola item toko server",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    def __init__(self, bot: AkizaBot) -> None:
        self.bot = bot

    async def _item_names(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        if interaction.guild is None:
            return []
        names = await self.bot.services.shop.search_names(interaction.guild.id, current)
        return [app_commands.Choice(name=n, value=n) for n in names]

    @app_commands.command(name="shop", description="Lihat item yang dijual di server ini")
    @app_commands.guild_only()
    async def shop(self, interaction: discord.Interaction) -> None:
        guild_id = await require_economy(self.bot, interaction)
        items = await self.bot.services.shop.list_items(guild_id)
        if not items:
            await interaction.response.send_message(
                "Toko masih kosong. Admin bisa menambah item dengan /shopadmin add.",
                ephemeral=True,
            )
            return
        lines = []
        for item in items[:25]:
            stock = "" if item.stock is None else f" (stok {item.stock})"
            desc = f"\n  {item.description}" if item.description else ""
            lines.append(f"**{item.name}** - {item.price} koin{stock}{desc}")
        await interaction.response.send_message(
            embed=discord.Embed(title="Toko", description="\n".join(lines))
        )

    @app_commands.command(name="buy", description="Beli item dari toko")
    @app_commands.describe(item="Nama item", amount="Jumlah (default 1)")
    @app_commands.guild_only()
    async def buy(
        self,
        interaction: discord.Interaction,
        item: str,
        amount: app_commands.Range[int, 1, 99] = 1,
    ) -> None:
        guild_id = await require_economy(self.bot, interaction)
        r = await self.bot.services.shop.buy(guild_id, interaction.user.id, item, amount)
        await interaction.response.send_message(
            f"Kamu membeli {r.quantity}x **{r.item_name}** seharga {r.total_cost} koin. "
            f"Saldo: **{r.balance}**."
        )

    @buy.autocomplete("item")
    async def buy_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._item_names(interaction, current)

    @app_commands.command(name="inventory", description="Lihat item yang kamu miliki")
    @app_commands.guild_only()
    async def inventory(self, interaction: discord.Interaction) -> None:
        guild_id = await require_economy(self.bot, interaction)
        entries = await self.bot.services.shop.inventory(guild_id, interaction.user.id)
        if not entries:
            await interaction.response.send_message("Inventory kamu kosong.", ephemeral=True)
            return
        text = "\n".join(f"{e.quantity}x **{e.name}**" for e in entries)
        await interaction.response.send_message(text, ephemeral=True)

    @shopadmin_group.command(name="add", description="Tambah item ke toko")
    @app_commands.describe(
        name="Nama item",
        price="Harga (koin)",
        stock="Stok (kosongkan = tak terbatas)",
        description="Deskripsi singkat",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shopadmin_add(
        self,
        interaction: discord.Interaction,
        name: str,
        price: int,
        stock: int | None = None,
        description: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        item = await self.bot.services.shop.add_item(
            interaction.guild.id, name, price, stock, description
        )
        await interaction.response.send_message(
            f"Item **{item.name}** ({item.price} koin) ditambahkan ke toko.", ephemeral=True
        )

    @shopadmin_group.command(name="remove", description="Hapus item dari toko")
    @app_commands.describe(name="Nama item")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def shopadmin_remove(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild is not None
        await self.bot.services.shop.remove_item(interaction.guild.id, name)
        await interaction.response.send_message(
            f"Item **{name}** dihapus dari toko (inventory pemain tetap aman).", ephemeral=True
        )

    @shopadmin_remove.autocomplete("name")
    async def remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self._item_names(interaction, current)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ShopCog(cast(AkizaBot, bot)))
