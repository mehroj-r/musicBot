import asyncio
import datetime
import itertools
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.filters.callback_data import CallbackData
from aiogram.methods import TelegramMethod
from aiogram.types import (
    Audio,
    CallbackQuery,
    Chat,
    ChatShared,
    Message,
    MessageEntity,
    MessageId,
    Update,
    User,
)

from musicbot.app import build_dispatcher
from musicbot.config import AudioFormat, Settings
from musicbot.db.database import Database
from musicbot.db.users import set_allowed, update_user
from musicbot.services.downloader import DownloadedTrack, Track
from musicbot.services.uploader import SentAudio
from musicbot.services.yandex import Account, DeviceCode, SignInStatus

BOT_TOKEN = "123456:TEST-token"
ADMIN_ID = 1
USER_ID = 42
CHANNEL_ID = -1001234567890
# Bot API methods that answer with a Message; everything else gets True
MESSAGE_METHODS = {"SendMessage", "EditMessageText", "SendAudio", "SendPhoto"}


def make_settings(**overrides) -> Settings:
    values = {"bot_token": BOT_TOKEN, "admin_ids": [ADMIN_ID], **overrides}
    # Ignore any developer .env so tests only see what they set
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(data_dir=tmp_path / "data")


@pytest.fixture
def database(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    database.migrate()
    yield database


@pytest.fixture
async def async_database(database: Database):
    yield database
    await database.close()


def make_audio_file(path: Path, codec_args: list[str]) -> Path:
    """
    Generate one second of silence with ffmpeg.
    """
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    generate = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1"]
    subprocess.run([*generate, *codec_args, str(path)], check=True)
    return path


class FakeSession(BaseSession):
    """
    Records every Bot API call instead of sending it, and answers with plausible results.
    """

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        # Canned results by method name, e.g. {"GetChatMember": ChatMemberAdministrator(...)}
        self.responses: dict[str, object] = {}
        self._ids = itertools.count(1000)

    # aiogram's BaseSession interface defines the timeout parameter
    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None):  # noqa: ASYNC109
        self.calls.append(method)
        name = type(method).__name__
        if name in self.responses:
            response = self.responses[name]
            if isinstance(response, Exception):
                raise response
            return response
        if name == "CopyMessage":
            return MessageId(message_id=next(self._ids))
        if name not in MESSAGE_METHODS:
            return True
        audio = None
        if name == "SendAudio":
            audio = Audio(file_id="file-id", file_unique_id="unique", duration=1)
        return Message(
            message_id=next(self._ids),
            date=datetime.datetime.now(datetime.UTC),
            chat=Chat(id=getattr(method, "chat_id", None) or 1, type="private"),
            text=getattr(method, "text", None),
            audio=audio,
        ).as_(bot)

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def close(self) -> None:
        pass

    def names(self) -> list[str]:
        return [type(call).__name__ for call in self.calls]

    def last(self, name: str) -> TelegramMethod:
        return [call for call in self.calls if type(call).__name__ == name][-1]


@dataclass
class FakeDownloader:
    error: Exception | None = None
    size: int = 1000
    # Reported as the track's identity for YouTube links, as yt-dlp would
    source_id: str = "abc123"
    # Pause after reporting progress, so the progress message can catch up
    delay: float = 0
    calls: list[tuple[str, AudioFormat]] = field(default_factory=list)

    def identify(self, url: str) -> tuple[str, str] | None:
        return ("Youtube", self.source_id) if "youtu" in url else None

    async def download(
        self, url: str, work_dir: Path, audio_format: AudioFormat, on_progress=None
    ) -> DownloadedTrack:
        self.calls.append((url, audio_format))
        if on_progress:
            on_progress("download", 0.5)
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        audio_path = work_dir / f"audio.{audio_format}"
        audio_path.write_bytes(b"\0" * self.size)
        cover_path = work_dir / "cover.jpg"
        cover_path.write_bytes(b"jpeg")
        track = Track(
            source="Youtube",
            source_id=self.source_id,
            title="Rock & <Roll>",
            artist="AC/DC",
            duration=254,
            webpage_url=url,
        )
        return DownloadedTrack(track, audio_format, audio_path, cover_path, None)


@dataclass
class FakeSender:
    max_size: int = 50 * 1024 * 1024
    error: Exception | None = None
    resend_error: Exception | None = None
    calls: list[tuple[int, DownloadedTrack, str]] = field(default_factory=list)
    resends: list[tuple[int, str | None, str]] = field(default_factory=list)
    _message_ids: itertools.count = field(default_factory=lambda: itertools.count(1))

    async def send_audio(self, chat_id: int, audio: DownloadedTrack, caption: str) -> SentAudio:
        assert audio.audio_path.exists(), "the file must still exist while it is uploaded"
        self.calls.append((chat_id, audio, caption))
        if self.error:
            raise self.error
        return SentAudio(chat_id=chat_id, message_id=next(self._message_ids), file_id="file-id")

    async def resend(self, chat_id: int, cached, caption: str) -> SentAudio:
        self.resends.append((chat_id, cached.file_id, caption))
        if self.resend_error:
            raise self.resend_error
        return SentAudio(
            chat_id=chat_id, message_id=next(self._message_ids), file_id=cached.file_id
        )


@dataclass
class FakeYandex:
    status_result: SignInStatus | None = None
    code_error: Exception | None = None
    # What waiting for the code ends with: the account signed in to, or an error
    sign_in_result: Account | Exception = field(
        default_factory=lambda: Account(login="music.fan", has_plus=True)
    )
    signed_out: bool = False

    async def status(self) -> SignInStatus | None:
        return self.status_result

    async def request_code(self) -> DeviceCode:
        if self.code_error:
            raise self.code_error
        return DeviceCode("device-secret", "abcd1234", "https://ya.ru/device", 300, 5)

    async def wait_for_sign_in(self, code: DeviceCode) -> Account:
        if isinstance(self.sign_in_result, Exception):
            raise self.sign_in_result
        return self.sign_in_result

    async def sign_out(self) -> None:
        self.signed_out = True


class Harness:
    """
    Feeds updates through the real dispatcher with fake Telegram, downloader and uploader.
    """

    def __init__(self, dispatcher, settings, database) -> None:
        self.session = FakeSession()
        self.bot = Bot(
            BOT_TOKEN, session=self.session, default=DefaultBotProperties(parse_mode="HTML")
        )
        self.dispatcher = dispatcher
        self.database = database
        self.downloader = FakeDownloader()
        self.sender = FakeSender()
        self.yandex = FakeYandex()
        self._update_ids = itertools.count(1)
        dispatcher.workflow_data.update(
            settings=settings,
            database=database,
            downloader=self.downloader,
            sender=self.sender,
            yandex=self.yandex,
            # A fresh semaphore per test: asyncio primitives bind to the loop they first wait on
            download_slots=asyncio.Semaphore(settings.max_parallel_downloads),
        )

    async def allow(self, user_id: int = USER_ID) -> None:
        async with self.database.session() as session:
            await set_allowed(session, user_id, True)

    async def set_channel(self, user_id: int = USER_ID, channel_id: int = CHANNEL_ID) -> None:
        async with self.database.session() as session:
            await update_user(session, user_id, channel_id=channel_id, channel_title="My <Music>")

    def calls_to(self, chat_id: int) -> list[TelegramMethod]:
        return [call for call in self.session.calls if getattr(call, "chat_id", None) == chat_id]

    async def send(
        self,
        text: str | None = None,
        user_id: int = USER_ID,
        first_name: str = "Test",
        chat_type: str = "private",
        entities: list[MessageEntity] | None = None,
        chat_shared: ChatShared | None = None,
    ) -> FakeSession:
        self.session.calls.clear()
        message = Message(
            message_id=next(self._update_ids),
            date=datetime.datetime.now(datetime.UTC),
            chat=Chat(id=user_id if chat_type == "private" else -100, type=chat_type),
            from_user=User(id=user_id, is_bot=False, first_name=first_name),
            text=text,
            entities=entities,
            chat_shared=chat_shared,
        )
        update = Update(update_id=next(self._update_ids), message=message)
        await self.dispatcher.feed_update(self.bot, update)
        return self.session

    async def press(self, data: CallbackData, user_id: int = USER_ID) -> FakeSession:
        """
        Press an inline button under a message the bot sent earlier, in bold "Old text".
        """
        self.session.calls.clear()
        message = Message(
            message_id=next(self._update_ids),
            date=datetime.datetime.now(datetime.UTC),
            chat=Chat(id=user_id, type="private"),
            text="Old text",
            entities=[MessageEntity(type="bold", offset=0, length=3)],
        )
        callback = CallbackQuery(
            id=str(next(self._update_ids)),
            from_user=User(id=user_id, is_bot=False, first_name="Presser"),
            chat_instance="chat",
            data=data.pack(),
            message=message,
        )
        update = Update(update_id=next(self._update_ids), callback_query=callback)
        await self.dispatcher.feed_update(self.bot, update)
        return self.session


@pytest.fixture(scope="session")
def dispatcher(tmp_path_factory):
    # Routers are module-level singletons, so the dispatcher is built once per session
    settings = make_settings(data_dir=tmp_path_factory.mktemp("data"))
    return build_dispatcher(
        settings=settings,
        database=None,
        downloader=FakeDownloader(),
        sender=FakeSender(),
        yandex=FakeYandex(),
    )


@pytest.fixture
async def harness(dispatcher, settings, async_database) -> Harness:
    return Harness(dispatcher, settings, async_database)


@pytest.fixture
async def allowed(harness: Harness) -> Harness:
    """
    A harness whose default user already has access.
    """
    await harness.allow()
    return harness
