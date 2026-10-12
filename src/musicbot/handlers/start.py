import html

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()

HELP_TEXT = (
    "Send me a link from YouTube, YouTube Music, Yandex Music, SoundCloud, Bandcamp or another "
    "supported site, and I'll turn it into an audio file.\n\n"
    "/start - Start the bot\n"
    "/settings - Choose the format, and a channel to post to\n"
    "/help - Show this message"
)
ADMIN_HELP_TEXT = (
    "\n\n<b>Admin</b>\n"
    "/allow USER_ID - Give someone access\n"
    "/revoke USER_ID - Take access away\n"
    "/users - List who has access\n"
    "/yandex - Sign in to Yandex Music"
)


@router.message(CommandStart())
async def start_handler(message: Message, is_new_user: bool) -> None:
    first_name = html.escape(message.from_user.first_name)

    if is_new_user:
        # Detailed message for new users
        greeting = (
            "<b>🎵 Welcome to the Music Assistant Bot! 🎵</b>\n\n"
            f"Hi <b>{first_name}</b>! 👋\n\n"
            "I save tracks and podcasts as <b>audio files</b> with title, artist and cover art.\n\n"
            "<b>How it works:</b>\n"
            "1️⃣ Send me a link from YouTube, YouTube Music, Yandex Music, SoundCloud, Bandcamp "
            "or a similar site\n"
            "2️⃣ I download and convert it to audio\n"
            "3️⃣ You get the audio here, or in your channel\n\n"
            "Use /settings to choose the format (M4A or MP3) or a channel to post to.\n\n"
            "<i>Let's get started. Send me a link!</i>"
        )
    else:
        # Shorter message for returning users
        greeting = (
            f"Welcome back, <b>{first_name}</b>! 👋\n"
            "Send me a link and I'll turn it into an audio file. 🎧"
        )

    await message.reply(greeting)


@router.message(Command("help"))
async def help_handler(message: Message, is_admin: bool = False) -> None:
    await message.reply(HELP_TEXT + ADMIN_HELP_TEXT if is_admin else HELP_TEXT)
