import asyncio

from yt_dlp.utils import DownloadError

from musicbot.config import AudioFormat
from musicbot.handlers.settings import SettingsCallback
from tests.conftest import ADMIN_ID, CHANNEL_ID, USER_ID, Harness

LINK = "https://youtu.be/pAgnJDJN4VA"


async def test_start_greets_new_then_returning_user(harness: Harness):
    # An admin: their first message creates the user row
    calls = await harness.send("/start", user_id=ADMIN_ID, first_name="<Mehroj>")
    greeting = calls.last("SendMessage").text
    assert "Welcome to the Music Assistant Bot" in greeting
    assert "&lt;Mehroj&gt;" in greeting

    calls = await harness.send("/start", user_id=ADMIN_ID)
    assert "Welcome back" in calls.last("SendMessage").text


async def test_users_allowed_before_writing_still_get_the_welcome(allowed: Harness):
    calls = await allowed.send("/start")
    assert "Welcome to the Music Assistant Bot" in calls.last("SendMessage").text


async def test_help_shows_admin_commands_only_to_admins(allowed: Harness):
    calls = await allowed.send("/help")
    assert "/settings" in calls.last("SendMessage").text
    assert "/allow" not in calls.last("SendMessage").text

    calls = await allowed.send("/help", user_id=ADMIN_ID)
    assert "/allow" in calls.last("SendMessage").text


async def test_link_is_sent_back_to_the_chat_by_default(allowed: Harness):
    calls = await allowed.send(f"check this {LINK}")

    assert allowed.downloader.calls == [(LINK, AudioFormat.M4A)]
    chat_id, audio, caption = allowed.sender.calls[0]
    assert chat_id == USER_ID
    assert caption == "🔉 <b>Rock &amp; &lt;Roll&gt;</b>"
    assert calls.names() == [
        "SendMessage",  # Downloading...
        "EditMessageText",  # Uploading...
        "DeleteMessage",  # status: the audio itself is the answer
        "DeleteMessage",  # the user's link
    ]
    # The job directory is gone once the handler returns
    assert not audio.audio_path.parent.exists()


async def test_link_is_posted_to_the_users_channel(allowed: Harness):
    await allowed.set_channel()

    calls = await allowed.send(LINK)

    assert allowed.sender.calls[0][0] == CHANNEL_ID
    confirmation = calls.last("EditMessageText").text
    assert "posted to" in confirmation
    assert 'href="https://t.me/c/1234567890/1"' in confirmation
    assert "My &lt;Music&gt;" in confirmation


async def test_preferred_format_is_used(allowed: Harness):
    await allowed.press(SettingsCallback(action="format", value="mp3"))
    await allowed.send(LINK)
    assert allowed.downloader.calls == [(LINK, AudioFormat.MP3)]


async def test_download_error_is_explained(allowed: Harness):
    allowed.downloader.error = DownloadError("ERROR: [youtube] x: This video is unavailable")

    calls = await allowed.send(LINK)

    assert calls.last("EditMessageText").text == "This video is unavailable."
    assert allowed.sender.calls == []
    assert "DeleteMessage" not in calls.names()


async def test_upload_failure_is_reported(allowed: Harness):
    allowed.sender.error = RuntimeError("Telegram is down")

    calls = await allowed.send(LINK)

    assert "Couldn't upload" in calls.last("EditMessageText").text
    assert "DeleteMessage" not in calls.names()


async def test_channel_post_failure_points_to_settings(allowed: Harness):
    await allowed.set_channel()
    allowed.sender.error = RuntimeError("Forbidden: bot is not a member of the channel")

    calls = await allowed.send(LINK)

    assert "/settings" in calls.last("EditMessageText").text


async def test_file_above_upload_limit_is_refused(allowed: Harness):
    allowed.downloader.size = 3 * 1024 * 1024
    allowed.sender.max_size = 2 * 1024 * 1024

    calls = await allowed.send(LINK)

    assert "above the 2 MB upload limit" in calls.last("EditMessageText").text
    assert allowed.sender.calls == []


async def test_text_without_link_gets_a_hint(allowed: Harness):
    calls = await allowed.send("hello")
    assert "Send me a link" in calls.last("SendMessage").text


async def test_group_messages_are_ignored(allowed: Harness):
    calls = await allowed.send(LINK, chat_type="group")
    assert calls.calls == []
    assert allowed.downloader.calls == []


async def test_waits_for_a_free_download_slot(allowed: Harness):
    slots = allowed.dispatcher.workflow_data["download_slots"]
    for _ in range(allowed.dispatcher.workflow_data["settings"].max_parallel_downloads):
        await slots.acquire()

    job = asyncio.create_task(allowed.send(LINK))
    await asyncio.sleep(0.05)
    assert allowed.session.calls[0].text.startswith("⏳ Waiting")
    assert allowed.downloader.calls == []

    slots.release()
    calls = await job
    assert calls.calls[1].text == "⬇️ Downloading..."
    assert len(allowed.sender.calls) == 1
