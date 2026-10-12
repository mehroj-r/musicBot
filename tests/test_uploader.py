import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiogram import Bot
from telethon.tl.types import DocumentAttributeAudio, DocumentAttributeFilename

from musicbot.config import MB, AudioFormat
from musicbot.services.downloader import DownloadedTrack, Track
from musicbot.services.uploader import AudioSender, SentAudio, TelethonUploader
from tests.conftest import BOT_TOKEN, FakeSession


def audio_of_size(tmp_path: Path, size: int) -> DownloadedTrack:
    path = tmp_path / "audio.m4a"
    path.touch()
    os.truncate(path, size)  # sparse, so big sizes cost no disk
    track = Track("Youtube", "abc", "Title", "Artist", 60, "")
    return DownloadedTrack(track, AudioFormat.M4A, path, None, None)


@dataclass
class FakeTelethon:
    calls: list[int] = field(default_factory=list)

    async def send_audio(self, chat_id: int, audio: DownloadedTrack, caption: str) -> SentAudio:
        self.calls.append(chat_id)
        return SentAudio(chat_id=chat_id, message_id=5, file_id=None)


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def bot(session: FakeSession) -> Bot:
    return Bot(BOT_TOKEN, session=session)


async def test_small_files_use_the_bot_api(tmp_path, bot, session):
    telethon = FakeTelethon()
    sender = AudioSender(bot, max_size=2000 * MB, telethon=telethon)

    sent = await sender.send_audio(7, audio_of_size(tmp_path, 10 * MB), caption="x")

    assert session.names() == ["SendAudio"]
    request = session.last("SendAudio")
    assert (request.title, request.performer, request.duration) == ("Title", "Artist", 60)
    assert request.audio.filename == "Artist - Title.m4a"
    assert sent.file_id == "file-id"
    assert telethon.calls == []


async def test_big_files_use_telethon(tmp_path, bot, session):
    telethon = FakeTelethon()
    sender = AudioSender(bot, max_size=2000 * MB, telethon=telethon)

    sent = await sender.send_audio(7, audio_of_size(tmp_path, 60 * MB), caption="x")

    assert telethon.calls == [7]
    assert session.calls == []
    assert sent.file_id is None


async def test_local_bot_api_server_takes_big_files_itself(tmp_path, bot, session):
    sender = AudioSender(bot, max_size=2000 * MB)
    await sender.send_audio(7, audio_of_size(tmp_path, 60 * MB), caption="x")
    assert session.names() == ["SendAudio"]


async def test_refuses_files_above_the_limit(tmp_path, bot, session):
    sender = AudioSender(bot, max_size=50 * MB)
    with pytest.raises(ValueError, match="upload limit"):
        await sender.send_audio(7, audio_of_size(tmp_path, 51 * MB), caption="x")
    assert session.calls == []


async def test_telethon_upload_sends_audio_attributes(tmp_path):
    uploader = TelethonUploader(tmp_path / "telethon", api_id=1, api_hash="hash")
    sent_kwargs = {}

    async def send_file(chat_id, **kwargs):
        sent_kwargs.update(chat_id=chat_id, **kwargs)
        return SimpleNamespace(id=99)

    uploader.client.send_file = send_file
    audio = audio_of_size(tmp_path, 60 * MB)

    sent = await uploader.send_audio(-100123, audio, caption="<b>Title</b>")

    assert sent == SentAudio(chat_id=-100123, message_id=99, file_id=None)
    assert (sent_kwargs["parse_mode"], sent_kwargs["mime_type"]) == ("html", "audio/mp4")
    audio_attribute, filename_attribute = sent_kwargs["attributes"]
    assert isinstance(audio_attribute, DocumentAttributeAudio)
    assert (audio_attribute.duration, audio_attribute.title, audio_attribute.performer) == (
        60,
        "Title",
        "Artist",
    )
    assert isinstance(filename_attribute, DocumentAttributeFilename)
    assert filename_attribute.file_name == "Artist - Title.m4a"
