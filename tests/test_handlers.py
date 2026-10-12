import asyncio

from yt_dlp.utils import DownloadError

from musicbot.config import AudioFormat
from tests.conftest import CHANNEL_ID, Harness

LINK = "https://youtu.be/pAgnJDJN4VA"


async def test_start_greets_new_then_returning_user(harness: Harness):
    calls = await harness.send("/start", first_name="<Mehroj>")
    greeting = calls.last("SendMessage").text
    assert "Welcome to the Music Assistant Bot" in greeting
    assert "&lt;Mehroj&gt;" in greeting

    calls = await harness.send("/start")
    assert "Welcome back" in calls.last("SendMessage").text


async def test_help(harness: Harness):
    calls = await harness.send("/help")
    assert "/start" in calls.last("SendMessage").text


async def test_link_is_downloaded_and_posted_to_channel(harness: Harness):
    calls = await harness.send(f"check this {LINK}")

    assert harness.downloader.calls == [(LINK, AudioFormat.MP3)]
    chat_id, audio, caption = harness.sender.calls[0]
    assert chat_id == CHANNEL_ID
    assert caption == "🔉 <b>Rock &amp; &lt;Roll&gt;</b>"
    assert calls.names() == [
        "SendMessage",  # Downloading...
        "EditMessageText",  # Uploading...
        "SendPhoto",  # confirmation with the cover
        "DeleteMessage",  # status
        "DeleteMessage",  # the user's link
    ]
    # The job directory is gone once the handler returns
    assert not audio.audio_path.parent.exists()


async def test_download_error_is_explained(harness: Harness):
    harness.downloader.error = DownloadError("ERROR: [youtube] x: This video is unavailable")

    calls = await harness.send(LINK)

    assert calls.last("EditMessageText").text == "This video is unavailable."
    assert harness.sender.calls == []
    assert "DeleteMessage" not in calls.names()


async def test_upload_failure_is_reported(harness: Harness):
    harness.sender.error = RuntimeError("Telegram is down")

    calls = await harness.send(LINK)

    assert "Couldn't upload" in calls.last("EditMessageText").text
    assert "DeleteMessage" not in calls.names()


async def test_file_above_upload_limit_is_refused(harness: Harness):
    harness.downloader.size = 3 * 1024 * 1024
    harness.sender.max_size = 2 * 1024 * 1024

    calls = await harness.send(LINK)

    assert "above the 2 MB upload limit" in calls.last("EditMessageText").text
    assert harness.sender.calls == []


async def test_text_without_link_gets_a_hint(harness: Harness):
    calls = await harness.send("hello")
    assert "Send me a link" in calls.last("SendMessage").text


async def test_group_messages_are_ignored(harness: Harness):
    calls = await harness.send(LINK, chat_type="group")
    assert calls.calls == []
    assert harness.downloader.calls == []


async def test_waits_for_a_free_download_slot(harness: Harness):
    slots = harness.dispatcher.workflow_data["download_slots"]
    for _ in range(harness.dispatcher.workflow_data["settings"].max_parallel_downloads):
        await slots.acquire()

    job = asyncio.create_task(harness.send(LINK))
    await asyncio.sleep(0.05)
    assert harness.session.calls[0].text.startswith("⏳ Waiting")
    assert harness.downloader.calls == []

    slots.release()
    calls = await job
    assert calls.calls[1].text == "⬇️ Downloading..."
    assert len(harness.sender.calls) == 1
