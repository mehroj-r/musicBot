from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types.bot_command import BotCommand
from aiogram import Dispatcher

from handlers import register_all_handlers
from config import settings
from utils.bot_utils import set_descripton, set_commands, set_short_description


# All handlers should be attached to the Router (or Dispatcher)
dp = Dispatcher()
register_all_handlers(dp)

bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

async def init_bot():
    await set_descripton(
        bot,
        "Lumi Service Bot - Your service bot in Telegram. \n\n "
        "I'm here to help you stay in touch with your bookings. \n\n "
        "Click /start to begin!")
    await set_short_description(
        bot,
        "Lumi Service Bot - Your service bot in Telegram")
    await set_commands(bot, [
        BotCommand(command="/start", description="Start the bot"),
        BotCommand(command="/help", description="Get help"),
        BotCommand(command="/settings", description="Change settings",),
    ])
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)