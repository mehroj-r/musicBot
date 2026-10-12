import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from musicbot.config import MB, Settings, UploadMode
from musicbot.db.database import Database
from musicbot.handlers import setup_routers
from musicbot.middlewares import UserMiddleware
from musicbot.services.downloader import Downloader
from musicbot.services.uploader import AudioSender, TelethonUploader

logger = logging.getLogger(__name__)


def create_bot(settings: Settings) -> Bot:
    session = None
    if settings.local_bot_api_url:
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(settings.local_bot_api_url, is_local=True)
        )
    return Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(
    settings: Settings, database: Database, downloader: Downloader, sender: AudioSender
) -> Dispatcher:
    # Everything passed here is injected into handlers and middlewares by name
    dispatcher = Dispatcher(
        settings=settings,
        database=database,
        downloader=downloader,
        sender=sender,
        download_slots=asyncio.Semaphore(settings.max_parallel_downloads),
    )
    dispatcher.message.outer_middleware(UserMiddleware())
    dispatcher.callback_query.outer_middleware(UserMiddleware())
    dispatcher.include_router(setup_routers())
    return dispatcher


async def configure_bot(bot: Bot) -> None:
    await bot.set_my_description(
        "Music Assistant Bot: saves audio from YouTube and other sites to Telegram.\n\n"
        "Click /start to begin!"
    )
    await bot.set_my_short_description("Saves audio from YouTube and other sites to Telegram.")
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="help", description="How to use the bot"),
        ]
    )


async def run(settings: Settings, database: Database) -> None:
    bot = create_bot(settings)

    telethon = None
    if settings.upload_mode is UploadMode.TELETHON:
        telethon = TelethonUploader(
            settings.data_dir / "telethon",
            settings.api_id,
            settings.api_hash.get_secret_value(),
        )

    dispatcher = build_dispatcher(
        settings=settings,
        database=database,
        downloader=Downloader(settings.cookies_file, settings.max_duration_minutes),
        sender=AudioSender(bot, settings.max_upload_size, telethon),
    )

    try:
        if telethon:
            await telethon.start(settings.bot_token.get_secret_value())
        logger.info(
            "Upload mode: %s (up to %d MB)", settings.upload_mode, settings.max_upload_size // MB
        )
        await configure_bot(bot)
        # Polling needs no webhook; keep updates sent while the bot was restarting
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot)
    finally:
        logger.info("Shutting down")
        if telethon:
            await telethon.close()
        await database.close()
        await bot.session.close()
