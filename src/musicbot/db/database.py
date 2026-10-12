from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

MIGRATIONS = "musicbot.db:migrations"


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    # WAL lets readers work while a download job writes
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def alembic_config(database_path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", MIGRATIONS)
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    return config


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        event.listen(self.engine.sync_engine, "connect", _set_sqlite_pragmas)
        self.session = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    def migrate(self) -> None:
        """
        Bring the schema up to date. Synchronous: call it before the event loop starts.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        command.upgrade(alembic_config(self.path), "head")

    async def close(self) -> None:
        await self.engine.dispose()
