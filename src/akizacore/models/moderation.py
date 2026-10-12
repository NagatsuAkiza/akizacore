from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from akizacore.database.base import Base


class ModWarning(Base):
    __tablename__ = "warnings"
    __table_args__ = (Index("ix_warnings_server_user", "server_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mod_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ModerationLog(Base):
    __tablename__ = "moderation_log"
    __table_args__ = (Index("ix_moderation_log_server_created", "server_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mod_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AutomodConfig(Base):
    __tablename__ = "automod_config"

    server_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    anti_spam: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spam_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    spam_window_s: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    anti_link: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_domains: Mapped[str] = mapped_column(Text, nullable=False, default="")
    action: Mapped[str] = mapped_column(String(16), nullable=False, default="delete")
    timeout_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
