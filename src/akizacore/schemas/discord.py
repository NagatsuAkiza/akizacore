from pydantic import BaseModel, ConfigDict


class UserInfo(BaseModel):
    """Data user dari Discord, sudah dinetralkan agar service tidak perlu import discord."""

    model_config = ConfigDict(frozen=True)

    id: int
    username: str
    avatar: str | None = None


class GuildInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    owner_id: int | None = None
