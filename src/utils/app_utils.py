import os

from aiogram.types import FSInputFile

from config.settings import CHANNEL_ID
from config.logging_conf import logger
from core.utils import get_current_time
from db.models import User
from services.telethon import TelethonService


async def send_photo(bot, chat_id, photo_path, caption):
    photo = FSInputFile(photo_path)
    await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption)


async def upload_to_telegram(bot, file_path, thumbnail_path, file_caption):
    if not os.path.isfile(file_path):
        logger.error("The specified file does not exist.")
        return
    try:
        audio_file = FSInputFile(file_path)
        thumbnail_file = FSInputFile(thumbnail_path)
        await bot.send_audio(
            chat_id=CHANNEL_ID,
            audio=audio_file,
            caption=f"🔉 <b>{file_caption}</b>",
            thumbnail=thumbnail_file
        )
    except Exception as e:
        logger.error(f"An error occurred while uploading the file: {e}")


async def upload_big_file(file_path: str, cover_image_path: str, data: dict[str, str]):
    await TelethonService.upload_files(file_path, cover_image_path, data)


def is_new_user(user: User) -> bool:
    diff = get_current_time() - user.created_at
    return diff.days == 0 and diff.seconds < 60