from datetime import timedelta

from aiogram.types import User as TelegramUser
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from musicbot.config import AudioFormat
from musicbot.db.base import Base
from musicbot.db.database import Database, alembic_config
from musicbot.db.tracks import find_cached, forget_cached, save_cached
from musicbot.db.users import (
    claim_access_request,
    list_allowed,
    set_allowed,
    update_user,
    upsert_user,
)
from musicbot.services.downloader import Track
from musicbot.services.uploader import SentAudio


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


async def test_allow_someone_who_never_wrote_to_the_bot(async_database: Database):
    async with async_database.session() as session:
        user = await set_allowed(session, 9, True)
    assert (user.is_allowed, user.display_name, user.audio_format) == (True, "9", AudioFormat.M4A)

    # Their name arrives with their first message, and access is kept
    async with async_database.session() as session:
        user, created = await upsert_user(
            session, TelegramUser(id=9, is_bot=False, first_name="Ann")
        )
    assert (created, user.is_allowed, user.display_name) == (True, True, "Ann")

    async with async_database.session() as session:
        await set_allowed(session, 9, False)
        assert await list_allowed(session) == []


async def test_access_requests_are_claimed_once_per_cooldown(async_database: Database):
    async with async_database.session() as session:
        await upsert_user(session, TelegramUser(id=5, is_bot=False, first_name="A"))
        assert await claim_access_request(session, 5, timedelta(hours=24))
        assert not await claim_access_request(session, 5, timedelta(hours=24))
        assert await claim_access_request(session, 5, timedelta(0))


async def test_preferences_round_trip(async_database: Database):
    async with async_database.session() as session:
        await upsert_user(session, TelegramUser(id=3, is_bot=False, first_name="A"))
        user = await update_user(session, 3, audio_format=AudioFormat.MP3, channel_id=-1001)
    assert user.audio_format is AudioFormat.MP3
    assert user.channel_id == -1001


def test_upgrade_keeps_existing_users(tmp_path):
    path = tmp_path / "old.db"
    config = alembic_config(path)
    command.upgrade(config, "0001")
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, first_name) VALUES (5, 'Old')"))

    command.upgrade(config, "head")

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT first_name, is_allowed, audio_format, channel_id FROM users")
        ).one()
    engine.dispose()
    assert tuple(row) == ("Old", 0, "m4a", None)


async def test_cache_entries_are_replaced_and_forgotten(async_database: Database):
    track = Track("Youtube", "abc", "Title", "Artist", 60, "")
    async with async_database.session() as session:
        await save_cached(session, track, AudioFormat.M4A, SentAudio(1, 10, "old"))
        await save_cached(session, track, AudioFormat.M4A, SentAudio(2, 20, "new"))
        await save_cached(session, track, AudioFormat.MP3, SentAudio(3, 30, None))

        cached = await find_cached(session, "Youtube", "abc", AudioFormat.M4A)
        assert (cached.chat_id, cached.message_id, cached.file_id) == (2, 20, "new")
        assert (await find_cached(session, "Youtube", "abc", AudioFormat.MP3)).file_id is None

        await forget_cached(session, cached.id)
        assert await find_cached(session, "Youtube", "abc", AudioFormat.M4A) is None
