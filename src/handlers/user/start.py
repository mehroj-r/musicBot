import datetime

from aiogram import types, Router
from aiogram.filters import CommandStart

from db.models import User
from utils.app_utils import is_new_user

router = Router()

@router.message(CommandStart())
async def start_handler(message: types.Message):
    user = message.from_user

    # Ensure the user is registered
    registered_user = await User.get_or_create(
        user_id=user.id,
        defaults = {
            "first_name": user.first_name,
            "username": user.username or "",
            "last_name": user.last_name or ""
        }
    )

    if not registered_user:
        await message.reply(
            "Sorry, I couldn't register you. Please try again later."
        )
        return

    if is_new_user(registered_user):
        # Detailed message for new users
        greeting_message = (
            "<b>🎵 Welcome to the Ultimate Audio Downloader Bot! 🎵</b>\n\n"
            f"Hi <b>{user.first_name}</b>! 👋\n\n"
            "I'm here to help you save your favorite tracks and podcasts as high-quality <b>audio files</b> with ease.\n\n"
            "<b>What can I do?</b>\n"
            "• Download audio from platforms like <b>YouTube</b>, <b>Spotify</b>, <b>Yandex Music</b>, <b>SoundCloud</b>, and more!\n"
            "• Send you audio files directly in your <b>private channel</b>\n\n"
            "<b>How it works:</b>\n"
            "1️⃣ Send me a link from any supported platform (YouTube, Spotify, Yandex Music, SoundCloud, etc.)\n"
            "2️⃣ I’ll convert it to audio\n"
            "3️⃣ You’ll get the file directly here on Telegram\n\n"
            "No need for complicated converters or shady websites.\n"
            "Enjoy seamless audio downloads from multiple sources — right here in Telegram! 🎧\n\n"
            "<i>Let’s get started. Send me a link!</i>"
        )
    else:
        # Shorter message for returning users
        greeting_message = (
            f"Welcome back, <b>{user.first_name}</b>! 👋\n"
            "Send me a link from YouTube, Spotify, Yandex Music, SoundCloud, or similar platforms, "
            "and I'll send you the audio file right here on Telegram. 🎧\n\n"
            "<i>Ready when you are!</i>"
        )

    await message.reply(greeting_message)