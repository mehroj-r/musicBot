import asyncio
import io
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from mutagen.mp4 import MP4
from PIL import Image
from yt_dlp.utils import DownloadError

from musicbot.config import AudioFormat
from musicbot.db.base import utcnow
from musicbot.db.database import Database
from musicbot.db.tokens import get_token, save_token
from musicbot.handlers import yandex as yandex_handlers
from musicbot.handlers.yandex import YandexCallback
from musicbot.services.downloader import Downloader, describe_error
from musicbot.services.yandex import (
    FILE_INFO_CLIENT,
    SERVICE,
    Account,
    DeviceCode,
    SignInStatus,
    YandexAuth,
    YandexError,
    file_info_sign,
)
from tests.conftest import ADMIN_ID, Harness, make_audio_file

YEAR = 365 * 24 * 3600
PENDING = {"error": "authorization_pending", "error_description": "User has not yet authorized"}
STATUS = {"account": {"login": "music.fan", "uid": 7}, "plus": {"hasPlus": True}}


@dataclass
class FakeYandexServer:
    """
    Yandex OAuth and the Yandex Music API, answering from canned data.
    """

    url: str = ""
    # Answers to POST /token, in order; the last one keeps repeating
    token_answers: list[dict[str, Any]] = field(default_factory=list)
    # Account status by token; any other token is rejected
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    # Track JSON by ID, and each track's files: codec -> (audio file, quality)
    tracks: dict[str, dict[str, Any]] = field(default_factory=dict)
    files: dict[str, dict[str, tuple[Path, str]]] = field(default_factory=dict)
    cover: bytes = b""
    # Codecs of the audio files downloaded
    downloads: list[str] = field(default_factory=list)

    def forms(self, path: str) -> list[dict[str, str]]:
        return [form for request_path, form in self.requests if request_path == path]

    def app(self) -> web.Application:
        async def record(request: web.Request) -> None:
            self.requests.append((request.path, dict(await request.post())))

        async def device_code(request: web.Request) -> web.Response:
            await record(request)
            return web.json_response(
                {
                    "device_code": "device-secret",
                    "user_code": "abcd1234",
                    "verification_url": "https://ya.ru/device",
                    "expires_in": 300,
                    "interval": 0,
                }
            )

        async def token(request: web.Request) -> web.Response:
            await record(request)
            answers = self.token_answers
            answer = answers.pop(0) if len(answers) > 1 else answers[0]
            return web.json_response(answer, status=400 if "error" in answer else 200)

        async def revoke(request: web.Request) -> web.Response:
            await record(request)
            return web.json_response({"status": "ok"})

        def account(request: web.Request) -> dict[str, Any] | None:
            return self.accounts.get(
                request.headers.get("Authorization", "").removeprefix("OAuth ")
            )

        def unauthorized() -> web.Response:
            return web.json_response({"status": 401, "error": "Unauthorized"}, status=401)

        async def account_status(request: web.Request) -> web.Response:
            if not account(request):
                return unauthorized()
            return web.json_response({"result": account(request)})

        async def track(request: web.Request) -> web.Response:
            if not account(request):
                return unauthorized()
            return web.json_response({"result": [self.tracks[request.match_info["track_id"]]]})

        async def file_info(request: web.Request) -> web.Response:
            if not account(request):
                return unauthorized()
            query = request.query
            codecs = query["codecs"].split(",")
            sign = file_info_sign(
                int(query["ts"]), query["trackId"], codecs, query["quality"], query["transports"]
            )
            client = request.headers.get("X-Yandex-Music-Client")
            if (query["sign"], client) != (sign, FILE_INFO_CLIENT):
                return web.json_response({"error": "Bad sign"}, status=400)

            track_files = self.files[query["trackId"]]
            codec = next(codec for codec in codecs if codec in track_files)
            info = {
                "trackId": query["trackId"],
                "quality": track_files[codec][1],
                "codec": codec,
                "bitrate": 192,
                "transport": "raw",
                "urls": [f"{self.url}/files/{query['trackId']}/{codec}"],
            }
            return web.json_response({"result": {"downloadInfo": info}})

        async def audio_file(request: web.Request) -> web.FileResponse:
            track_id, codec = request.match_info["track_id"], request.match_info["codec"]
            self.downloads.append(codec)
            return web.FileResponse(self.files[track_id][codec][0])

        async def cover(request: web.Request) -> web.Response:
            return web.Response(body=self.cover, content_type="image/jpeg")

        app = web.Application()
        app.router.add_post("/device/code", device_code)
        app.router.add_post("/token", token)
        app.router.add_post("/revoke_token", revoke)
        app.router.add_get("/account/status", account_status)
        app.router.add_get("/tracks/{track_id}", track)
        app.router.add_get("/get-file-info", file_info)
        app.router.add_get("/files/{track_id}/{codec}", audio_file)
        app.router.add_get("/cover/{size}", cover)
        return app


@pytest.fixture
async def yandex_server():
    fake = FakeYandexServer()
    server = TestServer(fake.app())
    await server.start_server()
    fake.url = str(server.make_url("")).rstrip("/")
    yield fake
    await server.close()


@pytest.fixture
async def auth(yandex_server: FakeYandexServer, async_database: Database):
    auth = YandexAuth(
        async_database,
        device_id="musicbot-1",
        oauth_url=yandex_server.url,
        api_url=yandex_server.url,
    )
    yield auth
    await auth.close()


async def store(database: Database, expires_in: timedelta, token: str = "token-1") -> None:
    async with database.session() as session:
        await save_token(session, SERVICE, token, "refresh-1", utcnow() + expires_in)


async def test_sign_in_with_a_code_stores_the_token(auth: YandexAuth, yandex_server):
    yandex_server.token_answers = [
        PENDING,
        {"access_token": "token-1", "refresh_token": "refresh-1", "expires_in": YEAR},
    ]
    yandex_server.accounts = {"token-1": STATUS}

    code = await auth.request_code()
    assert (code.user_code, code.verification_url) == ("abcd1234", "https://ya.ru/device")
    assert await auth.token() is None

    account = await auth.wait_for_sign_in(code)

    assert account == Account(login="music.fan", has_plus=True)
    assert await auth.token() == "token-1"
    async with auth.database.session() as session:
        stored = await get_token(session, SERVICE)
    assert stored.refresh_token == "refresh-1"
    assert timedelta(days=364) < stored.expires_at - utcnow() <= timedelta(days=365)

    # The same device ID every time, so Yandex replaces the bot's previous token
    assert yandex_server.forms("/device/code")[0]["device_id"] == "musicbot-1"
    polls = yandex_server.forms("/token")
    assert [poll["grant_type"] for poll in polls] == ["device_code", "device_code"]
    assert polls[0]["code"] == "device-secret"


async def test_refused_sign_in_stores_nothing(auth: YandexAuth, yandex_server):
    yandex_server.token_answers = [
        {"error": "access_denied", "error_description": "User denied access"}
    ]

    with pytest.raises(YandexError, match="User denied access"):
        await auth.wait_for_sign_in(await auth.request_code())
    assert await auth.token() is None


async def test_sign_in_gives_up_when_the_code_expires(auth: YandexAuth, yandex_server):
    yandex_server.token_answers = [PENDING]
    code = DeviceCode("device-secret", "abcd1234", "https://ya.ru/device", 0, 0)

    with pytest.raises(YandexError, match="expired"):
        await auth.wait_for_sign_in(code)


async def test_token_is_renewed_when_it_nears_expiry(auth: YandexAuth, yandex_server):
    await store(auth.database, timedelta(days=10))
    yandex_server.token_answers = [
        {"access_token": "token-2", "refresh_token": "refresh-2", "expires_in": YEAR}
    ]

    assert await auth.token() == "token-2"
    renewal = yandex_server.forms("/token")[0]
    assert (renewal["grant_type"], renewal["refresh_token"]) == ("refresh_token", "refresh-1")
    # Renewed once: the new token has a year left
    assert await auth.token() == "token-2"
    assert len(yandex_server.forms("/token")) == 1


async def test_fresh_token_is_not_renewed(auth: YandexAuth, yandex_server):
    await store(auth.database, timedelta(days=200))
    assert await auth.token() == "token-1"
    assert yandex_server.requests == []


async def test_failed_renewal_keeps_the_current_token(auth: YandexAuth, yandex_server):
    await store(auth.database, timedelta(days=10))
    yandex_server.token_answers = [{"error": "invalid_grant", "error_description": "Bad token"}]
    assert await auth.token() == "token-1"


async def test_status_checks_the_account(auth: YandexAuth, yandex_server):
    assert await auth.status() is None

    await store(auth.database, timedelta(days=200))
    yandex_server.accounts = {"token-1": {**STATUS, "plus": {"hasPlus": False}}}
    status = await auth.status()
    assert status.account == Account(login="music.fan", has_plus=False)
    assert not status.from_env
    assert status.expires_at - utcnow() > timedelta(days=199)

    yandex_server.accounts = {}
    status = await auth.status()
    assert status.account is None
    assert "no longer accepts" in status.error


async def test_token_from_the_environment_wins(yandex_server, async_database: Database):
    await store(async_database, timedelta(days=200))
    yandex_server.accounts = {"env-token": STATUS}
    auth = YandexAuth(
        async_database,
        device_id="musicbot-1",
        env_token="env-token",
        oauth_url=yandex_server.url,
        api_url=yandex_server.url,
    )

    assert await auth.token() == "env-token"
    status = await auth.status()
    assert (status.account.login, status.from_env, status.expires_at) == ("music.fan", True, None)
    await auth.close()


async def test_sign_out_forgets_and_revokes_the_token(auth: YandexAuth, yandex_server):
    await store(auth.database, timedelta(days=200))

    await auth.sign_out()

    assert await auth.token() is None
    assert yandex_server.forms("/revoke_token")[0]["access_token"] == "token-1"


async def test_unreachable_yandex_is_a_yandex_error(async_database: Database):
    # Nothing listens on the discard port
    auth = YandexAuth(async_database, device_id="musicbot-1", oauth_url="http://127.0.0.1:9")
    with pytest.raises(YandexError, match="didn't answer"):
        await auth.request_code()
    await auth.close()


async def finish_sign_ins() -> None:
    await asyncio.gather(*yandex_handlers.pending_sign_ins)


async def test_yandex_command_is_for_admins_only(allowed: Harness):
    calls = await allowed.send("/yandex")
    assert "Yandex Music" not in (calls.last("SendMessage").text or "")


async def test_yandex_command_offers_to_sign_in(harness: Harness):
    calls = await harness.send("/yandex", user_id=ADMIN_ID)

    reply = calls.last("SendMessage")
    assert "Not signed in" in reply.text
    buttons = [button.text for row in reply.reply_markup.inline_keyboard for button in row]
    assert buttons == ["🔑 Sign in"]


async def test_yandex_command_shows_the_account(harness: Harness):
    harness.yandex.status_result = SignInStatus(
        Account(login="<fan>", has_plus=False), expires_at=utcnow() + timedelta(days=30)
    )

    reply = (await harness.send("/yandex", user_id=ADMIN_ID)).last("SendMessage")

    assert "Signed in as <b>&lt;fan&gt;</b>" in reply.text
    assert "only 30-second previews" in reply.text
    buttons = [button.text for row in reply.reply_markup.inline_keyboard for button in row]
    assert buttons == ["🔑 Sign in again", "🚪 Sign out"]


async def test_yandex_command_with_token_from_the_environment(harness: Harness):
    harness.yandex.status_result = SignInStatus(None, from_env=True, error="Yandex is down")

    reply = (await harness.send("/yandex", user_id=ADMIN_ID)).last("SendMessage")

    assert "Yandex is down" in reply.text
    assert "YANDEX_MUSIC_TOKEN" in reply.text
    assert reply.reply_markup is None


async def test_sign_in_shows_the_code_then_the_account(harness: Harness):
    calls = await harness.press(YandexCallback(action="sign_in"), user_id=ADMIN_ID)

    code_message = calls.last("SendMessage")
    assert code_message.chat_id == ADMIN_ID
    assert "<code>abcd1234</code>" in code_message.text
    assert code_message.reply_markup.inline_keyboard[0][0].url == "https://ya.ru/device"

    await finish_sign_ins()
    outcome = calls.last("EditMessageText").text
    assert outcome == "✅ Signed in to Yandex Music as <b>music.fan</b>."


async def test_sign_in_warns_about_an_account_without_plus(harness: Harness):
    harness.yandex.sign_in_result = Account(login="music.fan", has_plus=False)
    calls = await harness.press(YandexCallback(action="sign_in"), user_id=ADMIN_ID)
    await finish_sign_ins()
    assert "no Yandex Plus" in calls.last("EditMessageText").text


async def test_failed_sign_in_is_reported(harness: Harness):
    harness.yandex.sign_in_result = YandexError("The code expired before it was entered")
    calls = await harness.press(YandexCallback(action="sign_in"), user_id=ADMIN_ID)
    await finish_sign_ins()
    assert calls.last("EditMessageText").text.startswith(
        "❌ Couldn't sign in to Yandex Music: The code expired before it was entered."
    )


async def test_sign_in_when_yandex_is_unreachable(harness: Harness):
    harness.yandex.code_error = YandexError("Yandex didn't answer (timeout)")

    calls = await harness.press(YandexCallback(action="sign_in"), user_id=ADMIN_ID)

    answer = calls.last("AnswerCallbackQuery")
    assert answer.show_alert
    assert "didn't answer" in answer.text
    assert "SendMessage" not in calls.names()


async def test_sign_out(harness: Harness):
    calls = await harness.press(YandexCallback(action="sign_out"), user_id=ADMIN_ID)

    assert harness.yandex.signed_out
    assert "Not signed in" in calls.last("EditMessageText").text


def test_file_info_sign_matches_the_yandex_music_library():
    # Computed with yandex-music 3.2.2's get_file_info_sign
    sign = file_info_sign(1700000000, "139305800", ["aac-mp4", "mp3"], "lossless", "raw")
    assert sign == "adM5BHivWHHfAo8BG1HwViM1XZy6C0IuiT0WuA4XCA4"


class StaticToken:
    def __init__(self, token: str | None) -> None:
        self._token = token

    async def token(self) -> str | None:
        return self._token


def track_json(track_id: str, url: str, **overrides: Any) -> dict[str, Any]:
    return {
        "id": track_id,
        "title": "Bohemian Rhapsody",
        "version": "Remastered 2011",
        "available": True,
        "durationMs": 1000,
        "artists": [{"name": "Queen"}, {"name": "<Guest>"}],
        "albums": [
            {"id": 9, "title": "A Night at the Opera", "year": 1975, "coverUri": f"{url}/cover/%%"}
        ],
        **overrides,
    }


@pytest.fixture
def yandex_api(yandex_server: FakeYandexServer, monkeypatch, tmp_path: Path) -> FakeYandexServer:
    """
    The fake Yandex Music API with track 1 in AAC and MP3, and track 2 in MP3 only.
    """
    monkeypatch.setattr("musicbot.services.yandex.API_URL", yandex_server.url)
    yandex_server.accounts = {"token-1": STATUS}

    aac = make_audio_file(tmp_path / "song.m4a", ["-c:a", "aac", "-b:a", "192k"])
    mp3 = make_audio_file(tmp_path / "song.mp3", ["-c:a", "libmp3lame", "-b:a", "192k"])
    cover = io.BytesIO()
    Image.new("RGB", (1000, 1000), "red").save(cover, "JPEG")
    yandex_server.cover = cover.getvalue()

    for track_id in ("1", "2"):
        yandex_server.tracks[track_id] = track_json(track_id, yandex_server.url)
    yandex_server.files["1"] = {"aac-mp4": (aac, "nq"), "mp3": (mp3, "nq")}
    yandex_server.files["2"] = {"mp3": (mp3, "nq")}
    return yandex_server


async def download(tmp_path: Path, url: str, audio_format: AudioFormat, token: str = "token-1"):
    job = tmp_path / "job"
    job.mkdir()
    return await Downloader(None, 180, StaticToken(token)).download(url, job, audio_format)


async def test_yandex_track_as_m4a_keeps_its_aac(yandex_api: FakeYandexServer, tmp_path: Path):
    audio = await download(tmp_path, "https://music.yandex.ru/album/9/track/1", AudioFormat.M4A)

    assert yandex_api.downloads == ["aac-mp4"]
    track = audio.track
    assert (track.source, track.source_id, track.duration) == ("YandexMusic", "1", 1)
    assert track.title == "Bohemian Rhapsody (Remastered 2011)"
    assert track.artist == "Queen, <Guest>"
    assert audio.audio_path.suffix == ".m4a"
    tags = MP4(audio.audio_path).tags
    assert tags["\xa9nam"] == ["Bohemian Rhapsody (Remastered 2011)"]
    assert "covr" in tags
    assert audio.thumbnail_path is not None


async def test_yandex_track_as_mp3_is_its_own_mp3(yandex_api: FakeYandexServer, tmp_path: Path):
    audio = await download(tmp_path, "https://music.yandex.com/track/1", AudioFormat.MP3)

    assert yandex_api.downloads == ["mp3"]
    assert audio.audio_path.suffix == ".mp3"


async def test_mp3_only_yandex_track_is_converted_for_m4a(
    yandex_api: FakeYandexServer, tmp_path: Path
):
    audio = await download(tmp_path, "https://music.yandex.ru/track/2", AudioFormat.M4A)

    assert yandex_api.downloads == ["mp3"]
    assert MP4(audio.audio_path).info.codec.startswith("mp4a")


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"quality": "preview"}, "30-second preview"),
        ({"token": "revoked"}, "no longer accepts the bot's sign-in"),
        ({"available": False}, "isn't available on Yandex Music"),
    ],
)
async def test_yandex_download_failures_are_explained(
    yandex_api: FakeYandexServer, tmp_path: Path, change: dict[str, Any], expected: str
):
    if "quality" in change:
        yandex_api.files["1"] = {"mp3": (yandex_api.files["1"]["mp3"][0], change["quality"])}
    if "available" in change:
        yandex_api.tracks["1"]["available"] = change["available"]

    with pytest.raises(DownloadError) as error:
        url = "https://music.yandex.ru/track/1"
        await download(tmp_path, url, AudioFormat.M4A, change.get("token", "token-1"))

    assert expected in describe_error(error.value)
    assert yandex_api.downloads == []
