import os

from aiogram import types, Router, F, Bot

from config.logging_config import logger
from services.yt_dlp import DLPService
from utils.app_utils import upload_to_telegram, send_photo, upload_big_file

router = Router()

@router.message(F.text.startswith("https://"))
async def echo_message(message: types.Message) -> None:

    # Check if the message text is a valid YouTube URL
    if not (
            message.text.startswith("https://www.youtube.com/watch?")
            or message.text.startswith("https://youtu.be/")
            or message.text.startswith("https://youtube.com/watch?")
    ):
        await message.reply("Invalid URL")


    # Send a message indicating that the download is in progress
    downloading_sent = await message.reply("Downloading ...", disable_web_page_preview=True)

    # Download the audio file and get the file location, thumbnail location, caption, and metadata
    try:
        file_location, thumbnail_location, file_caption, data = DLPService.download_audio(url=message.text)
    except Exception as e:
        logger.error(f"An error occurred while downloading audio: {e}")
        await downloading_sent.edit_text(
            text=f"An error occured"
        )
        return None

    # After downloading is done, update the message to indicate that the download is complete
    await downloading_sent.edit_text(
        text=f"<b>🎵 {data['title']}</b>\n\nDownloading - DONE\nUploading ...",
    )

    # Upload the file to Telegram according to its size
    try:
        if os.path.getsize(file_location) > 52428800:
            await upload_big_file(file_location, thumbnail_location, data)
        else:
            await upload_to_telegram(message.bot, file_location, thumbnail_location, file_caption)
    except Exception as e:
        logger.error(f"An error occurred while uploading the file: {e}")
        await downloading_sent.edit_text(
            text=f"An error occurred",
        )
        return None

    # After the upload is complete, send a message with the thumbnail and caption in the chat
    await send_photo(
        bot=message.bot,
        chat_id=message.chat.id,
        photo_path=thumbnail_location,
        caption=f"<b>🎵 {data['title']}</b>\n\nSuccessfully uploaded to the channel."
    )

    # Clean up the files after upload
    os.remove(file_location)
    os.remove(thumbnail_location)

    # Delete the messages
    await downloading_sent.delete()
    await message.delete()

    return None