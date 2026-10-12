"""moderation tables

Revision ID: 0004
Revises: 0003
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warnings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("mod_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_warnings_server_user", "warnings", ["server_id", "user_id"])
    op.create_table(
        "moderation_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("server_id", sa.BigInteger(), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("mod_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_moderation_log_server_created", "moderation_log", ["server_id", "created_at"])
    op.create_table(
        "automod_config",
        sa.Column("server_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("anti_spam", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("spam_messages", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("spam_window_s", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("anti_link", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allowed_domains", sa.Text(), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=16), nullable=False, server_default="delete"),
        sa.Column("timeout_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.PrimaryKeyConstraint("server_id"),
    )


def downgrade() -> None:
    op.drop_table("automod_config")
    op.drop_index("ix_moderation_log_server_created", table_name="moderation_log")
    op.drop_table("moderation_log")
    op.drop_index("ix_warnings_server_user", table_name="warnings")
    op.drop_table("warnings")
