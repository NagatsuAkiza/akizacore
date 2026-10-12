from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from akizacore.database.base import Base, TimestampMixin


class Server(TimestampMixin, Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class ServerSettings(TimestampMixin, Base):
    __tablename__ = "settings"

    server_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True
    )
    log_channel_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    welcome_channel_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    autorole_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    ai_persona: Mapped[str | None] = mapped_column(Text, default=None)
    features: Mapped[dict[str, bool]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
