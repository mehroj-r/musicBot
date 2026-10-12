import asyncio
import html
import logging
import tempfile
from pathlib import Path

from aiogram import Router
from aiogram.types import LinkPreviewOptions, Message
from yt_dlp.utils import DownloadError

from musicbot.config import MB
from musicbot.db.models import User
from musicbot.services.downloader import Downloader, DownloadRejected, describe_error
from musicbot.services.links import has_link
from musicbot.services.uploader import AudioSender

logger = logging.getLogger(__name__)

router = Router()


def message_link(chat_id: int, message_id: int) -> str:
    # Works for channel members, which the user is: t.me/c/<ID without -100>/<message>
    return f"https://t.me/c/{str(chat_id).removeprefix('-100')}/{message_id}"


@router.message(has_link)
async def download_handler(
    message: Message,
    url: str,
    db_user: User,
    downloader: Downloader,
    sender: AudioSender,
    download_slots: asyncio.Semaphore,
) -> None:
    # The user's channel if they set one in /settings, otherwise this chat
    channel = html.escape(db_user.channel_title or "your channel")
    destination = db_user.channel_id or message.chat.id

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
                audio = await downloader.download(url, Path(work_dir), db_user.audio_format)
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
                sent = await sender.send_audio(destination, audio, caption=f"🔉 <b>{title}</b>")
            except Exception:
                logger.exception("Upload failed for %s", url)
                if db_user.channel_id:
                    reason = (
                        f"Couldn't post to <b>{channel}</b>. Make sure I'm still an admin there "
                        "with permission to post, or change the channel in /settings."
                    )
                else:
                    reason = "Couldn't upload the audio."
                await status.edit_text(f"<b>🎵 {title}</b>\n\n{reason}")
                return

    if db_user.channel_id:
        link = message_link(sent.chat_id, sent.message_id)
        await status.edit_text(
            f'✅ <b>{title}</b> was posted to <a href="{link}">{channel}</a>.',
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    else:
        # The audio itself is the answer; tidy the chat around it
        await status.delete()
    await message.delete()
