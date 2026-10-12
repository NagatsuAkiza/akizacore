from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import akizacore.models  # noqa: F401
from akizacore.config import DatabaseSettings
from akizacore.database import Base, build_session_factory

TEST_DB = "akizacore_test"


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Database test terpisah (akizacore_test), dibuat otomatis dan di-reset tiap test."""
    base_url = make_url(DatabaseSettings().database_url)
    admin = create_async_engine(
        base_url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    except Exception as exc:
        pytest.skip(f"PostgreSQL tidak tersedia (jalankan: docker compose up -d): {exc}")
    finally:
        await admin.dispose()

    engine = create_async_engine(base_url.set(database=TEST_DB), poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield build_session_factory(engine)
    await engine.dispose()
