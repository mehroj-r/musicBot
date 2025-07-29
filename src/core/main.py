import asyncio

from core.bot import init_bot
from config.logging_conf import logger
from core.db import init_db


async def main() -> None:
    try:
        await init_db()
        await init_bot()
    except Exception as e:
        logger.error(f"Fatal error in main process: {e}")
        raise
    finally:
        logger.info("Shutting down all services...")

if __name__ == "__main__":
    asyncio.run(main())