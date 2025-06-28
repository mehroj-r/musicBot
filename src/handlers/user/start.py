from aiogram import types, Router
from aiogram.filters import CommandStart

router = Router()

@router.message(CommandStart())
async def start_handler(message: types.Message):
    user = message.from_user

    # Greet the user
    await message.reply(
        "<b>🎵 Welcome to the YouTube Audio Downloader Bot! 🎵</b>\n\n"
        f"Hi <b>{user.first_name}</b>! 👋\n\n"
        "I'm here to help you save your favorite YouTube videos as high-quality <b>audio files</b> with ease.\n\n"
        "<b>How it works:</b>\n"
        "1️⃣ Send me a YouTube video link\n"
        "2️⃣ I’ll convert it to audio\n"
        "3️⃣ You’ll get the file directly in your <b>private channel</b>\n\n"
        "Forget about complicated converters or shady websites.\n"
        "Enjoy seamless audio downloads — right here in Telegram! 🎧\n\n"
        "<i>Let’s get started. Send me a link!</i>"
    )