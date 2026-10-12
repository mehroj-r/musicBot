import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, ErrorEvent

from musicbot.config import MB, Settings, UploadMode
from musicbot.db.database import Database
from musicbot.handlers import setup_routers
from musicbot.middlewares import AccessMiddleware, UserMiddleware
from musicbot.services.downloader import Downloader
from musicbot.services.uploader import AudioSender, TelethonUploader
from musicbot.services.yandex import YandexAuth

logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="Start the bot"),
    BotCommand(command="settings", description="Format and destination"),
    BotCommand(command="help", description="How to use the bot"),
]
ADMIN_COMMANDS = [
    *USER_COMMANDS,
    BotCommand(command="allow", description="Give someone access"),
    BotCommand(command="revoke", description="Take access away"),
    BotCommand(command="users", description="List who has access"),
    BotCommand(command="yandex", description="Sign in to Yandex Music"),
]


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


async def handle_error(event: ErrorEvent) -> None:
    """
    Last resort for exceptions in handlers: log them, and give the user feedback so a
    pressed button doesn't keep spinning.
    """
    logger.error("Failed to handle update %s", event.update.update_id, exc_info=event.exception)
    text = "Something went wrong. Please try again."
    with contextlib.suppress(TelegramAPIError):
        if event.update.callback_query:
            await event.update.callback_query.answer(text, show_alert=True)
        elif event.update.message:
            await event.update.message.answer(text)


def build_dispatcher(
    settings: Settings,
    database: Database,
    downloader: Downloader,
    sender: AudioSender,
    yandex: YandexAuth,
) -> Dispatcher:
    # Everything passed here is injected into handlers and middlewares by name
    dispatcher = Dispatcher(
        settings=settings,
        database=database,
        downloader=downloader,
        sender=sender,
        yandex=yandex,
        download_slots=asyncio.Semaphore(settings.max_parallel_downloads),
    )
    # Order matters: users are registered before their access is checked
    for observer in (dispatcher.message, dispatcher.callback_query):
        observer.outer_middleware(UserMiddleware())
        observer.outer_middleware(AccessMiddleware())
    dispatcher.errors.register(handle_error)
    dispatcher.include_router(setup_routers())
    return dispatcher


async def configure_bot(bot: Bot, settings: Settings) -> None:
    await bot.set_my_description(
        "Music Assistant Bot: saves audio from YouTube, Yandex Music and other sites to "
        "Telegram.\n\n"
        "Click /start to begin!"
    )
    await bot.set_my_short_description(
        "Saves audio from YouTube, Yandex Music and other sites to Telegram."
    )
    await bot.set_my_commands(USER_COMMANDS)
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except TelegramAPIError as e:
            logger.warning("Couldn't set admin commands for %s (bot not started?): %s", admin_id, e)


async def run(settings: Settings, database: Database) -> None:
    bot = create_bot(settings)

    telethon = None
    if settings.upload_mode is UploadMode.TELETHON:
        telethon = TelethonUploader(
            settings.data_dir / "telethon",
            settings.api_id,
            settings.api_hash.get_secret_value(),
        )

    env_token = settings.yandex_music_token
    yandex = YandexAuth(
        database,
        # Stable per bot, so signing in again replaces the bot's previous Yandex token
        device_id=f"musicbot-{bot.id}",
        env_token=env_token.get_secret_value() if env_token else None,
    )

    dispatcher = build_dispatcher(
        settings=settings,
        database=database,
        downloader=Downloader(settings.cookies_file, settings.max_duration_minutes, yandex),
        sender=AudioSender(bot, settings.max_upload_size, telethon),
        yandex=yandex,
    )

    try:
        if telethon:
            await telethon.start(settings.bot_token.get_secret_value())
        logger.info(
            "Upload mode: %s (up to %d MB)", settings.upload_mode, settings.max_upload_size // MB
        )
        if not settings.admin_ids:
            logger.warning("ADMIN_IDS is empty, so nobody can use the bot")
        await configure_bot(bot, settings)
        # Polling needs no webhook; keep updates sent while the bot was restarting
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot)
    finally:
        logger.info("Shutting down")
        if telethon:
            await telethon.close()
        await yandex.close()
        await database.close()
        await bot.session.close()
