from datetime import UTC, datetime

DISCORD_EPOCH_MS = 1420070400000


def snowflake_to_datetime(snowflake: int) -> datetime:
    """Waktu pembuatan akun/objek Discord dari ID-nya (dipakai untuk syarat umur akun)."""
    return datetime.fromtimestamp(((snowflake >> 22) + DISCORD_EPOCH_MS) / 1000, tz=UTC)
