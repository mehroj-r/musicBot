import asyncio
import contextlib
import html
import logging
import tempfile
from pathlib import Path

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import LinkPreviewOptions, Message
from yt_dlp.utils import DownloadError

from musicbot.config import MB
from musicbot.db.database import Database
from musicbot.db.models import User
from musicbot.db.tracks import find_cached, forget_cached, save_cached
from musicbot.services.downloader import Downloader, DownloadRejected, describe_error
from musicbot.services.links import has_link
from musicbot.services.uploader import AudioSender, SentAudio

logger = logging.getLogger(__name__)

router = Router()

# Telegram limits how often a message can be edited; this stays well below it
PROGRESS_INTERVAL = 3.0


class ProgressMessage:
    """
    Shows download progress in the status message, editing it at most every few seconds.
    """

    def __init__(self, status: Message, text: str) -> None:
        self.status = status
        self.text = self.shown = text
        self._task: asyncio.Task | None = None

    def report(self, stage: str, fraction: float | None) -> None:
        # Runs in yt-dlp's thread: only store the text, the loop below sends it
        if stage == "convert":
            self.text = "🎛 Converting..."
        elif fraction is not None:
            self.text = f"⬇️ Downloading... {fraction:.0%}"

    async def _keep_updated(self) -> None:
        while True:
            await asyncio.sleep(PROGRESS_INTERVAL)
            text = self.text
            if text != self.shown:
                with contextlib.suppress(TelegramAPIError):
                    await self.status.edit_text(text)
                self.shown = text

    async def __aenter__(self) -> "ProgressMessage":
        self._task = asyncio.create_task(self._keep_updated())
        return self

    async def __aexit__(self, *exc_info) -> None:
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task


def message_link(chat_id: int, message_id: int) -> str:
    # Works for channel members, which the user is: t.me/c/<ID without -100>/<message>
    return f"https://t.me/c/{str(chat_id).removeprefix('-100')}/{message_id}"


async def send_cached(
    url: str,
    destination: int,
    db_user: User,
    database: Database,
    downloader: Downloader,
    sender: AudioSender,
) -> tuple[SentAudio, str] | None:
    """
    Send the track again if it was uploaded before in this format.

    :return: Where it was sent and its escaped title, or None when it has to be downloaded.
    """
    key = await asyncio.to_thread(downloader.identify, url)
    if key is None:
        return None
    async with database.session() as session:
        cached = await find_cached(session, *key, db_user.audio_format)
    if cached is None:
        return None

    title = html.escape(cached.title)
    try:
        sent = await sender.resend(destination, cached, caption=f"🔉 <b>{title}</b>")
    except TelegramAPIError as e:
        # The file or the first post is gone: download it again
        logger.info("Cached %s:%s is no longer usable: %s", *key, e)
        async with database.session() as session:
            await forget_cached(session, cached.id)
        return None
    return sent, title


@router.message(has_link)
async def download_handler(
    message: Message,
    url: str,
    db_user: User,
    database: Database,
    downloader: Downloader,
    sender: AudioSender,
    download_slots: asyncio.Semaphore,
) -> None:
    # The user's channel if they set one in /settings, otherwise this chat
    channel = html.escape(db_user.channel_title or "your channel")
    destination = db_user.channel_id or message.chat.id

    if cached := await send_cached(url, destination, db_user, database, downloader, sender):
        sent, title = cached
        if db_user.channel_id:
            link = message_link(sent.chat_id, sent.message_id)
            await message.answer(
                f'✅ <b>{title}</b> was posted to <a href="{link}">{channel}</a>.',
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        await message.delete()
        return

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
                async with ProgressMessage(status, "⬇️ Downloading...") as progress:
                    audio = await downloader.download(
                        url, Path(work_dir), db_user.audio_format, on_progress=progress.report
                    )
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

    # Next time this track is requested in this format, it is sent without downloading
    async with database.session() as session:
        await save_cached(session, audio.track, db_user.audio_format, sent)

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
