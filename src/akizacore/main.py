import asyncio

from akizacore.config import get_settings
from akizacore.core.bot import AkizaBot
from akizacore.core.logging import setup_logging


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, json_output=settings.environment == "prod")
    async with AkizaBot(settings) as bot:
        await bot.start(settings.discord_token.get_secret_value())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
