import html

from aiogram.types import FSInputFile

from config.settings import CHANNEL_ID
from core.templates import AudioData
from core.utils import get_current_time
from db.models import User
from services.telethon import TelethonService

# Bot API refuses uploads above 50 MB; bigger files go through Telethon
BOT_API_UPLOAD_LIMIT = 50 * 1024 * 1024


async def send_photo(bot, chat_id, photo_path, caption):
    photo = FSInputFile(photo_path)
    await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)


async def upload_to_telegram(bot, audio: AudioData) -> None:
    await bot.send_audio(
        chat_id=CHANNEL_ID,
        audio=FSInputFile(audio.file_path),
        caption=f"🔉 <b>{html.escape(audio.title)}</b>",
        title=audio.title,
        performer=audio.artist,
        duration=audio.duration,
        thumbnail=FSInputFile(audio.thumbnail_path) if audio.thumbnail_path else None,
        request_timeout=300,
    )


async def upload_big_file(audio: AudioData) -> None:
    await TelethonService.upload_files(audio)


def is_new_user(user: User) -> bool:
    diff = get_current_time() - user.created_at
    return diff.days == 0 and diff.seconds < 60
