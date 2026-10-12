from aiogram.types import User as TelegramUser
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from musicbot.db.base import Base
from musicbot.db.database import Database
from musicbot.db.users import upsert_user


def test_migrations_match_models(database: Database):
    engine = create_engine(f"sqlite:///{database.path}")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []
    engine.dispose()


async def test_upsert_creates_then_updates(async_database: Database):
    async with async_database.session() as session:
        user, created = await upsert_user(
            session, TelegramUser(id=7, is_bot=False, first_name="Old", username="old")
        )
    assert created
    assert (user.id, user.first_name, user.username) == (7, "Old", "old")

    async with async_database.session() as session:
        updated, created = await upsert_user(
            session, TelegramUser(id=7, is_bot=False, first_name="New")
        )
    assert not created
    assert (updated.first_name, updated.username) == ("New", None)
    assert updated.created_at == user.created_at
    assert updated.created_at.tzinfo is not None


async def test_connections_use_wal(async_database: Database):
    async with async_database.session() as session:
        journal_mode = (await session.execute(text("PRAGMA journal_mode"))).scalar_one()
        foreign_keys = (await session.execute(text("PRAGMA foreign_keys"))).scalar_one()
    assert (journal_mode, foreign_keys) == ("wal", 1)
