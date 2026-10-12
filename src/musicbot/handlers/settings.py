import html

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    ChatAdministratorRights,
    ChatMemberAdministrator,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from musicbot.config import AudioFormat
from musicbot.db.database import Database
from musicbot.db.models import User
from musicbot.db.users import update_user

router = Router()

CHANNEL_REQUEST_ID = 1
CANCEL_TEXT = "✖️ Cancel"

FORMAT_DESCRIPTIONS = {
    AudioFormat.M4A: "M4A, original quality without re-encoding",
    AudioFormat.MP3: "MP3, plays everywhere (re-encoded at 192 kbps)",
}

# The only right the bot needs in a channel. Telegram also requires the user to hold
# every right the bot asks for, so the same rights are requested from the user.
POST_RIGHTS = ChatAdministratorRights(
    is_anonymous=False,
    can_manage_chat=False,
    can_delete_messages=False,
    can_manage_video_chats=False,
    can_restrict_members=False,
    can_promote_members=False,
    can_change_info=False,
    can_invite_users=False,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
    can_send_welcome_messages=False,
    can_post_messages=True,
)


class SettingsCallback(CallbackData, prefix="settings"):
    action: str  # "format", "channel" or "clear"
    value: str = ""


def render_settings(user: User) -> tuple[str, InlineKeyboardMarkup]:
    if user.channel_id:
        destination = f"📢 {html.escape(user.channel_title or str(user.channel_id))}"
    else:
        destination = "💬 This chat"
    text = (
        "⚙️ <b>Settings</b>\n\n"
        f"<b>Format:</b> {FORMAT_DESCRIPTIONS[user.audio_format]}\n"
        f"<b>Audio goes to:</b> {destination}"
    )

    keyboard = InlineKeyboardBuilder()
    for audio_format in AudioFormat:
        mark = "✅ " if audio_format is user.audio_format else ""
        keyboard.button(
            text=f"{mark}{audio_format.upper()}",
            callback_data=SettingsCallback(action="format", value=audio_format),
        )
    keyboard.button(
        text="📢 Change channel" if user.channel_id else "📢 Post to a channel",
        callback_data=SettingsCallback(action="channel"),
    )
    if user.channel_id:
        keyboard.button(text="💬 Send here instead", callback_data=SettingsCallback(action="clear"))
    keyboard.adjust(len(AudioFormat), 1, 1)
    return text, keyboard.as_markup()


async def show_settings(callback: CallbackQuery, user: User) -> None:
    text, markup = render_settings(user)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.message(Command("settings"))
async def settings_command(message: Message, db_user: User) -> None:
    text, markup = render_settings(db_user)
    await message.answer(text, reply_markup=markup)


@router.callback_query(SettingsCallback.filter(F.action == "format"))
async def change_format(
    callback: CallbackQuery, callback_data: SettingsCallback, database: Database, db_user: User
) -> None:
    audio_format = AudioFormat(callback_data.value)
    if audio_format is db_user.audio_format:
        # Editing the message to the same content is an error in Telegram
        await callback.answer()
        return

    async with database.session() as session:
        user = await update_user(session, db_user.id, audio_format=audio_format)
    await show_settings(callback, user)


@router.callback_query(SettingsCallback.filter(F.action == "clear"))
async def clear_channel(callback: CallbackQuery, database: Database, db_user: User) -> None:
    async with database.session() as session:
        user = await update_user(session, db_user.id, channel_id=None, channel_title=None)
    await show_settings(callback, user)


@router.callback_query(SettingsCallback.filter(F.action == "channel"))
async def ask_for_channel(callback: CallbackQuery) -> None:
    # Telegram's native picker lists the user's channels and adds the bot as an admin
    picker = KeyboardButtonRequestChat(
        request_id=CHANNEL_REQUEST_ID,
        chat_is_channel=True,
        user_administrator_rights=POST_RIGHTS,
        bot_administrator_rights=POST_RIGHTS,
        request_title=True,
    )
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📢 Choose a channel", request_chat=picker)],
            [KeyboardButton(text=CANCEL_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "Pick a channel you manage. Telegram will add me there with permission to post.",
            reply_markup=keyboard,
        )
    await callback.answer()


@router.message(F.chat_shared.request_id == CHANNEL_REQUEST_ID)
async def channel_chosen(message: Message, bot: Bot, database: Database, db_user: User) -> None:
    shared = message.chat_shared
    try:
        member = await bot.get_chat_member(shared.chat_id, bot.id)
    except TelegramAPIError:
        member = None
    if not (isinstance(member, ChatMemberAdministrator) and member.can_post_messages):
        await message.answer(
            "I can't post in that channel. Make me an admin there with permission to post, "
            "then choose it again in /settings.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    title = shared.title or str(shared.chat_id)
    async with database.session() as session:
        user = await update_user(
            session, db_user.id, channel_id=shared.chat_id, channel_title=title
        )
    await message.answer(
        f"✅ Your audio will be posted to <b>{html.escape(title)}</b>.",
        reply_markup=ReplyKeyboardRemove(),
    )
    text, markup = render_settings(user)
    await message.answer(text, reply_markup=markup)


@router.message(F.text == CANCEL_TEXT)
async def cancel(message: Message) -> None:
    await message.answer("Okay, nothing changed.", reply_markup=ReplyKeyboardRemove())
