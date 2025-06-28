import asyncio

from src.core.bot import init_bot
from config.logging_config import logger

async def main() -> None:
    try:
        await init_bot()
    except Exception as e:
        logger.error(f"Fatal error in main process: {e}")
        raise
    finally:
        logger.info("Shutting down all services...")

if __name__ == "__main__":
    asyncio.run(main())