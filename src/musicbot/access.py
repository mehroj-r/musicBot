import html
import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from musicbot.db.models import User

logger = logging.getLogger(__name__)

# Ask the admins about the same person at most once a day
REQUEST_COOLDOWN = timedelta(hours=24)


class AccessCallback(CallbackData, prefix="access"):
    action: str  # "allow" or "ignore"
    user_id: int


def mention(user: User) -> str:
    text = f'<a href="tg://user?id={user.id}">{html.escape(user.display_name)}</a>'
    if user.username:
        text += f" (@{html.escape(user.username)})"
    return text


async def notify_admins(bot: Bot, admin_ids: list[int], user: User) -> None:
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Allow", callback_data=AccessCallback(action="allow", user_id=user.id))
    keyboard.button(
        text="🚫 Ignore", callback_data=AccessCallback(action="ignore", user_id=user.id)
    )
    text = f"🔐 <b>Access request</b>\n\n{mention(user)}\nID: <code>{user.id}</code>"

    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=keyboard.as_markup())
        except TelegramAPIError as e:
            # Typically an admin who never started the bot
            logger.warning("Couldn't notify admin %s: %s", admin_id, e)


async def notify_granted(bot: Bot, user_id: int) -> None:
    try:
        await bot.send_message(user_id, "✅ You now have access. Send me a link to get started!")
    except TelegramAPIError as e:
        logger.info("Couldn't tell user %s about their access: %s", user_id, e)
