import html
import os
import re
import shutil

from aiogram import types, Router, F

from config.logging_conf import logger
from services.yt_dlp import DLPService
from utils.app_utils import BOT_API_UPLOAD_LIMIT, upload_to_telegram, send_photo, upload_big_file
from utils.dlp_utils import describe_download_error

router = Router()

YOUTUBE_URL = re.compile(
    r"^https?://(?:(?:www|m|music)\.)?(?:youtube\.com/(?:watch\?|shorts/)|youtu\.be/)",
    re.IGNORECASE,
)

@router.message(F.text.regexp(r"^https?://"))
async def download_audio(message: types.Message) -> None:
    url = message.text.strip()

    # Check if the message text is a valid YouTube URL
    if not YOUTUBE_URL.match(url):
        await message.reply("Invalid URL")
        return None

    # Send a message indicating that the download is in progress
    downloading_sent = await message.reply("Downloading ...", disable_web_page_preview=True)

    # Download the audio file along with its metadata and cover art
    try:
        audio_data = await DLPService.download(url=url)
    except Exception as e:
        logger.error(f"An error occurred while downloading audio: {e}")
        await downloading_sent.edit_text(text=describe_download_error(e))
        return None

    title = html.escape(audio_data.title)

    try:
        # After downloading is done, update the message to indicate that the download is complete
        await downloading_sent.edit_text(
            text=f"<b>🎵 {title}</b>\n\nDownloading - DONE\nUploading ...",
        )

        # Upload the file to Telegram according to its size
        if os.path.getsize(audio_data.file_path) > BOT_API_UPLOAD_LIMIT:
            await upload_big_file(audio_data)
        else:
            await upload_to_telegram(message.bot, audio_data)

        # After the upload is complete, report back in the chat
        done_text = f"<b>🎵 {title}</b>\n\nSuccessfully uploaded to the channel."
        if audio_data.cover_path:
            await send_photo(
                bot=message.bot,
                chat_id=message.chat.id,
                photo_path=audio_data.cover_path,
                caption=done_text,
            )
        else:
            await message.answer(done_text)
    except Exception as e:
        logger.error(f"An error occurred while uploading the file: {e}")
        await downloading_sent.edit_text(text="An error occurred while uploading the file.")
        return None
    finally:
        # Clean up the files whether or not the upload succeeded
        shutil.rmtree(audio_data.work_dir, ignore_errors=True)

    # Delete the messages
    await downloading_sent.delete()
    await message.delete()

    return None
