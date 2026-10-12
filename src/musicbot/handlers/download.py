import asyncio
import html
import logging
import tempfile
from pathlib import Path

from aiogram import Router
from aiogram.types import FSInputFile, LinkPreviewOptions, Message
from yt_dlp.utils import DownloadError

from musicbot.config import MB, AudioFormat, Settings
from musicbot.services.downloader import Downloader, DownloadRejected, describe_error
from musicbot.services.links import has_link
from musicbot.services.uploader import AudioSender

logger = logging.getLogger(__name__)

router = Router()


@router.message(has_link)
async def download_handler(
    message: Message,
    url: str,
    settings: Settings,
    downloader: Downloader,
    sender: AudioSender,
    download_slots: asyncio.Semaphore,
) -> None:
    queued = download_slots.locked()
    status = await message.reply(
        "⏳ Waiting for a free download slot..." if queued else "⬇️ Downloading...",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )

    async with download_slots:
        with tempfile.TemporaryDirectory(prefix="musicbot-") as work_dir:
            if queued:
                await status.edit_text("⬇️ Downloading...")

            try:
                audio = await downloader.download(url, Path(work_dir), AudioFormat.MP3)
            except Exception as e:
                # yt-dlp failures are expected; anything else is a bug worth a traceback
                expected = isinstance(e, (DownloadError, DownloadRejected))
                logger.warning("Download failed for %s: %s", url, e, exc_info=not expected)
                await status.edit_text(describe_error(e))
                return

            title = html.escape(audio.track.title)
            if audio.size > sender.max_size:
                await status.edit_text(
                    f"<b>🎵 {title}</b> is {audio.size // MB} MB, "
                    f"above the {sender.max_size // MB} MB upload limit."
                )
                return

            await status.edit_text(f"<b>🎵 {title}</b>\n\n⬆️ Uploading...")
            try:
                await sender.send_audio(settings.channel_id, audio, caption=f"🔉 <b>{title}</b>")
            except Exception:
                logger.exception("Upload failed for %s", url)
                await status.edit_text(f"<b>🎵 {title}</b>\n\nCouldn't upload the audio.")
                return

            # Report back in the chat with the cover art, if there is one
            done_text = f"<b>🎵 {title}</b>\n\nSuccessfully uploaded to the channel."
            if audio.cover_path:
                await message.answer_photo(FSInputFile(audio.cover_path), caption=done_text)
            else:
                await message.answer(done_text)

    await status.delete()
    await message.delete()
