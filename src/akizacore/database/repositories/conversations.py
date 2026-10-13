import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from akizacore.models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(self, server_id: int, user_id: int, channel_id: int) -> uuid.UUID:
        base = insert(Conversation).values(
            id=uuid.uuid4(), server_id=server_id, user_id=user_id, channel_id=channel_id
        )
        stmt = base.on_conflict_do_update(
            index_elements=[Conversation.server_id, Conversation.user_id, Conversation.channel_id],
            set_={"last_active_at": func.now()},
        ).returning(Conversation.id)
        return (await self.session.execute(stmt)).scalar_one()

    async def recent_messages(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        rows = list((await self.session.scalars(stmt)).all())
        rows.reverse()
        return rows

    async def add_messages(
        self, conversation_id: uuid.UUID, items: Sequence[tuple[str, str, int]]
    ) -> None:
        """items: (role, content, tokens)"""
        self.session.add_all(
            Message(conversation_id=conversation_id, role=role, content=content, tokens=tokens)
            for role, content, tokens in items
        )
        await self.session.flush()

    async def purge_older_than(self, cutoff: datetime) -> tuple[int, int]:
        """Hapus pesan lama, lalu percakapan yang sudah lama tidak aktif (sisa pesannya ikut terhapus)."""
        messages = await self.session.execute(delete(Message).where(Message.created_at < cutoff))
        conversations = await self.session.execute(
            delete(Conversation).where(Conversation.last_active_at < cutoff)
        )
        return (
            max(int(getattr(messages, "rowcount", 0) or 0), 0),
            max(int(getattr(conversations, "rowcount", 0) or 0), 0),
        )

    async def delete_for_user(self, server_id: int, user_id: int) -> int:
        stmt = (
            delete(Conversation)
            .where(Conversation.server_id == server_id, Conversation.user_id == user_id)
            .returning(Conversation.id)
        )
        return len((await self.session.execute(stmt)).all())

    async def count_messages_for_server(self, server_id: int) -> int:
        stmt = (
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.server_id == server_id)
        )
        return int((await self.session.execute(stmt)).scalar_one() or 0)
