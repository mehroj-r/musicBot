import logging
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeFilename

from musicbot.config import MB
from musicbot.db.models import CachedTrack
from musicbot.services.downloader import DownloadedTrack

logger = logging.getLogger(__name__)

# The cloud Bot API refuses uploads above this size
BOT_API_UPLOAD_LIMIT = 50 * MB


@dataclass(frozen=True)
class SentAudio:
    chat_id: int
    message_id: int
    # Only Bot API uploads report a file ID
    file_id: str | None


class TelethonUploader:
    """
    Uploads files above the Bot API limit over MTProto, logged in as the bot itself.
    """

    def __init__(self, session_path: Path, api_id: int, api_hash: str) -> None:
        session_path.parent.mkdir(parents=True, exist_ok=True)
        # aiogram handles updates; this client only uploads
        self.client = TelegramClient(str(session_path), api_id, api_hash, receive_updates=False)

    async def start(self, bot_token: str) -> None:
        await self.client.start(bot_token=bot_token)
        logger.info("Telethon client started")

    async def close(self) -> None:
        await self.client.disconnect()

    async def send_audio(self, chat_id: int, audio: DownloadedTrack, caption: str) -> SentAudio:
        track = audio.track
        message = await self.client.send_file(
            chat_id,
            file=str(audio.audio_path),
            caption=caption,
            parse_mode="html",
            mime_type=audio.audio_format.mime_type,
            thumb=str(audio.thumbnail_path) if audio.thumbnail_path else None,
            attributes=[
                DocumentAttributeAudio(
                    duration=track.duration or 0, title=track.title, performer=track.artist
                ),
                DocumentAttributeFilename(audio.file_name),
            ],
        )
        return SentAudio(chat_id=chat_id, message_id=message.id, file_id=None)


class AudioSender:
    def __init__(self, bot: Bot, max_size: int, telethon: TelethonUploader | None = None) -> None:
        self.bot = bot
        self.max_size = max_size
        self.telethon = telethon

    async def send_audio(self, chat_id: int, audio: DownloadedTrack, caption: str) -> SentAudio:
        size = audio.size
        if size > self.max_size:
            raise ValueError(f"{size} bytes is above the {self.max_size} byte upload limit")

        if self.telethon and size > BOT_API_UPLOAD_LIMIT:
            return await self.telethon.send_audio(chat_id, audio, caption)

        track = audio.track
        message = await self.bot.send_audio(
            chat_id=chat_id,
            audio=FSInputFile(audio.audio_path, filename=audio.file_name),
            caption=caption,
            title=track.title,
            performer=track.artist,
            duration=track.duration,
            thumbnail=FSInputFile(audio.thumbnail_path) if audio.thumbnail_path else None,
            # Allow for slow links: at least 2 minutes, plus a second per 512 kB
            request_timeout=120 + size // (512 * 1024),
        )
        file_id = message.audio.file_id if message.audio else None
        return SentAudio(chat_id=message.chat.id, message_id=message.message_id, file_id=file_id)

    async def resend(self, chat_id: int, cached: CachedTrack, caption: str) -> SentAudio:
        """
        Send a track uploaded before, without uploading it again.
        Raises TelegramAPIError when the file or the first post is gone.
        """
        if cached.file_id:
            message = await self.bot.send_audio(
                chat_id=chat_id, audio=cached.file_id, caption=caption
            )
            file_id = message.audio.file_id if message.audio else cached.file_id
            return SentAudio(
                chat_id=message.chat.id, message_id=message.message_id, file_id=file_id
            )

        # Uploaded with Telethon: copy the first post instead
        copied = await self.bot.copy_message(
            chat_id=chat_id,
            from_chat_id=cached.chat_id,
            message_id=cached.message_id,
            caption=caption,
        )
        return SentAudio(chat_id=chat_id, message_id=copied.message_id, file_id=None)
