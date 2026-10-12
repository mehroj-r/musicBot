from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendAudio

import musicbot.handlers.download
from musicbot.config import AudioFormat
from musicbot.db.tracks import find_cached
from musicbot.db.users import set_allowed, update_user
from tests.conftest import CHANNEL_ID, USER_ID, Harness

LINK = "https://youtu.be/pAgnJDJN4VA"
OTHER_USER = 77


async def allow_other_user(harness: Harness, **preferences) -> None:
    async with harness.database.session() as session:
        await set_allowed(session, OTHER_USER, True)
        if preferences:
            await update_user(session, OTHER_USER, **preferences)


async def test_second_request_is_sent_from_the_cache(allowed: Harness):
    await allowed.send(LINK)
    await allow_other_user(allowed)

    calls = await allowed.send(LINK, user_id=OTHER_USER)

    assert len(allowed.downloader.calls) == 1
    assert allowed.sender.resends == [(OTHER_USER, "file-id", "🔉 <b>Rock &amp; &lt;Roll&gt;</b>")]
    # No status message: the audio arrives straight away and the link is tidied up
    assert calls.names() == ["DeleteMessage"]


async def test_cached_post_to_a_channel_is_confirmed(allowed: Harness):
    await allowed.send(LINK)
    await allow_other_user(allowed, channel_id=CHANNEL_ID, channel_title="Tunes")

    calls = await allowed.send(LINK, user_id=OTHER_USER)

    assert allowed.sender.resends[0][0] == CHANNEL_ID
    assert "posted to" in calls.last("SendMessage").text


async def test_cache_is_per_format(allowed: Harness):
    await allowed.send(LINK)
    await allow_other_user(allowed, audio_format=AudioFormat.MP3)

    await allowed.send(LINK, user_id=OTHER_USER)

    assert allowed.downloader.calls == [(LINK, AudioFormat.M4A), (LINK, AudioFormat.MP3)]
    assert allowed.sender.resends == []


async def test_unusable_cache_entry_is_downloaded_again(allowed: Harness):
    await allowed.send(LINK)
    allowed.sender.resend_error = TelegramBadRequest(SendAudio, "wrong file identifier")

    await allowed.send(LINK)

    assert len(allowed.downloader.calls) == 2
    async with allowed.database.session() as session:
        cached = await find_cached(session, "Youtube", "abc123", AudioFormat.M4A)
    # Replaced by the new upload
    assert cached.message_id == 2


async def test_failed_upload_is_not_cached(allowed: Harness):
    allowed.sender.error = RuntimeError("Telegram is down")
    await allowed.send(LINK)

    async with allowed.database.session() as session:
        assert await find_cached(session, "Youtube", "abc123", AudioFormat.M4A) is None


async def test_links_without_an_offline_id_are_downloaded(allowed: Harness):
    await allowed.send("https://soundcloud.com/artist/track")
    await allowed.send("https://soundcloud.com/artist/track")
    assert len(allowed.downloader.calls) == 2


async def test_progress_is_shown_while_downloading(allowed: Harness, monkeypatch):
    monkeypatch.setattr(musicbot.handlers.download, "PROGRESS_INTERVAL", 0.01)
    allowed.downloader.delay = 0.1

    calls = await allowed.send(LINK)

    edits = [call.text for call in calls.calls if type(call).__name__ == "EditMessageText"]
    assert "⬇️ Downloading... 50%" in edits
    assert USER_ID in [call[0] for call in allowed.sender.calls]
