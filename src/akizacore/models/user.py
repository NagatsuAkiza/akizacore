from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from akizacore.database.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(100))
    avatar: Mapped[str | None] = mapped_column(String(255), default=None)
    global_name: Mapped[str | None] = mapped_column(String(100), default=None)


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(10), default="id", server_default="id")
    timezone: Mapped[str] = mapped_column(
        String(64), default="Asia/Jakarta", server_default="Asia/Jakarta"
    )
    ai_prefs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    ai_opt_out: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
