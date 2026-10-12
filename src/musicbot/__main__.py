import asyncio

from musicbot.app import run
from musicbot.config import Settings
from musicbot.db.database import Database
from musicbot.log import setup_logging


def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level)

    database = Database(settings.database_path)
    # Alembic runs synchronously, so migrate before the event loop starts
    database.migrate()

    asyncio.run(run(settings, database))


if __name__ == "__main__":
    main()
