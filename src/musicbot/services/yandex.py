import asyncio
import base64
import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.networking.exceptions import HTTPError
from yt_dlp.utils import ExtractorError, float_or_none, int_or_none

from musicbot.db.base import utcnow
from musicbot.db.database import Database
from musicbot.db.tokens import delete_token, get_token, save_token

logger = logging.getLogger(__name__)

OAUTH_URL = "https://oauth.yandex.ru"
API_URL = "https://api.music.yandex.net"
# The Yandex Music Android app's OAuth client, which every third-party Yandex Music client
# uses: apps registered by anyone else don't get access to Yandex Music
CLIENT_ID = "23cabbbdc6cd418abb4b39c32c41195d"
CLIENT_SECRET = "53bc75238f0c4d08a118e51fe9203300"
MUSIC_CLIENT = "YandexMusicAndroid/24026191"
# get-file-info requests are signed with the desktop app's key, which Yandex checks against
# the client header
FILE_INFO_CLIENT = "YandexMusicDesktopAppWindows/5.95.0"
FILE_INFO_SIGN_KEY = b"kzqU4XhfCaY6B6JTHODeq5"
# Extension and codec of the files Yandex Music serves unencrypted, by its codec name
FILE_CODECS = {"aac-mp4": ("m4a", "aac"), "he-aac-mp4": ("m4a", "aac"), "mp3": ("mp3", "mp3")}
# How the sign-in is listed among the account's devices at id.yandex.ru
DEVICE_NAME = "Music Bot (Telegram)"
SERVICE = "yandex_music"
# Tokens last a year; renew once less than this is left
RENEW_BEFORE = timedelta(days=30)
TIMEOUT = aiohttp.ClientTimeout(total=20)


class YandexError(Exception):
    """
    Yandex refused a request or didn't answer; the message is safe to show to admins.
    """


class TokenRejected(YandexError):
    """
    Yandex no longer accepts the token: someone has to sign in again.
    """


@dataclass(frozen=True)
class DeviceCode:
    # Secret: the bot polls with it until the user code is entered
    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class Account:
    login: str
    has_plus: bool


@dataclass(frozen=True)
class SignInStatus:
    # None when the account couldn't be checked; ``error`` says why
    account: Account | None
    from_env: bool = False
    expires_at: datetime | None = None
    error: str | None = None


def oauth_error(data: dict[str, Any]) -> str:
    return data.get("error_description") or data.get("error") or f"unexpected answer {data}"


class YandexAuth:
    """
    Signs the bot in to Yandex Music with a code entered at ya.ru/device, and keeps the
    token renewed. YANDEX_MUSIC_TOKEN, when set, is used instead and never renewed.
    """

    def __init__(
        self,
        database: Database,
        device_id: str,
        env_token: str | None = None,
        oauth_url: str = OAUTH_URL,
        api_url: str = API_URL,
    ) -> None:
        self.database = database
        # The same ID on every sign-in, so Yandex replaces the previous token
        self.device_id = device_id
        self.env_token = env_token
        self.oauth_url = oauth_url
        self.api_url = api_url
        self._http: aiohttp.ClientSession | None = None
        self._renewing = asyncio.Lock()

    def _session(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession(timeout=TIMEOUT)
        return self._http

    async def close(self) -> None:
        if self._http:
            await self._http.close()

    async def _oauth(self, path: str, **form: str) -> dict[str, Any]:
        """
        POST to Yandex OAuth. Its errors come back as JSON too, so they're returned, not raised.
        """
        form = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, **form}
        try:
            async with self._session().post(f"{self.oauth_url}{path}", data=form) as response:
                return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as e:
            raise YandexError(f"Yandex didn't answer ({e or type(e).__name__})") from e

    async def _save(self, data: dict[str, Any]) -> tuple[str, datetime | None]:
        expires_in = data.get("expires_in")
        expires_at = utcnow() + timedelta(seconds=int(expires_in)) if expires_in else None
        async with self.database.session() as session:
            await save_token(
                session, SERVICE, data["access_token"], data.get("refresh_token"), expires_at
            )
        return data["access_token"], expires_at

    async def request_code(self) -> DeviceCode:
        data = await self._oauth("/device/code", device_id=self.device_id, device_name=DEVICE_NAME)
        if "device_code" not in data:
            raise YandexError(oauth_error(data))
        return DeviceCode(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_url=data["verification_url"],
            expires_in=int(data["expires_in"]),
            interval=int(data["interval"]),
        )

    async def wait_for_sign_in(self, code: DeviceCode) -> Account:
        """
        Wait until the code is entered at its verification URL, then store the token.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + code.expires_in
        while loop.time() < deadline:
            await asyncio.sleep(code.interval)
            try:
                data = await self._oauth("/token", grant_type="device_code", code=code.device_code)
            except YandexError as e:
                # A network hiccup shouldn't end the sign-in; the code is still valid
                logger.warning("Checking the Yandex sign-in failed: %s", e)
                continue
            if data.get("error") == "authorization_pending":
                continue
            if "access_token" not in data:
                raise YandexError(oauth_error(data))

            account = await self.account(data["access_token"])
            await self._save(data)
            logger.info("Signed in to Yandex Music as %s", account.login)
            return account
        raise YandexError("The code expired before it was entered")

    async def account(self, token: str) -> Account:
        headers = {"Authorization": f"OAuth {token}", "X-Yandex-Music-Client": MUSIC_CLIENT}
        url = f"{self.api_url}/account/status"
        try:
            async with self._session().get(url, headers=headers) as response:
                if response.status in (401, 403):
                    raise TokenRejected("Yandex no longer accepts the sign-in")
                response.raise_for_status()
                result = (await response.json())["result"]
                account = result["account"]
        except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError) as e:
            raise YandexError(f"Yandex Music didn't answer ({e or type(e).__name__})") from e
        return Account(
            login=account.get("login") or str(account.get("uid")),
            has_plus=bool((result.get("plus") or {}).get("hasPlus")),
        )

    async def _current(self) -> tuple[str, datetime | None] | None:
        """
        The token and when it expires, renewed first when it gets close to expiring.
        """
        if self.env_token:
            return self.env_token, None

        async with self._renewing:
            async with self.database.session() as session:
                stored = await get_token(session, SERVICE)
            if stored is None:
                return None

            expires_at = stored.expires_at
            if stored.refresh_token and expires_at and expires_at - utcnow() < RENEW_BEFORE:
                try:
                    data = await self._oauth(
                        "/token", grant_type="refresh_token", refresh_token=stored.refresh_token
                    )
                    if "access_token" not in data:
                        raise YandexError(oauth_error(data))
                    logger.info("Renewed the Yandex Music token")
                    return await self._save(data)
                except YandexError as e:
                    # The current token keeps working until it expires
                    logger.warning("Couldn't renew the Yandex Music token: %s", e)
            return stored.access_token, expires_at

    async def token(self) -> str | None:
        """
        The token to call Yandex Music with, or None when the bot isn't signed in.
        """
        current = await self._current()
        return current[0] if current else None

    async def status(self) -> SignInStatus | None:
        """
        Who the bot is signed in as, checked with Yandex; None when it isn't signed in.
        """
        current = await self._current()
        if current is None:
            return None
        token, expires_at = current
        from_env = bool(self.env_token)
        try:
            account = await self.account(token)
        except YandexError as e:
            return SignInStatus(None, from_env, expires_at, error=str(e))
        return SignInStatus(account, from_env, expires_at)

    async def sign_out(self) -> None:
        async with self.database.session() as session:
            stored = await get_token(session, SERVICE)
            if stored is None:
                return
            await delete_token(session, SERVICE)

        # Also invalidate it at Yandex; the bot has forgotten it either way
        try:
            await self._oauth("/revoke_token", access_token=stored.access_token)
        except YandexError as e:
            logger.warning("Couldn't revoke the Yandex Music token: %s", e)
        logger.info("Signed out of Yandex Music")


def file_info_sign(
    timestamp: int, track_id: str, codecs: list[str], quality: str, transport: str
) -> str:
    message = f"{timestamp}{track_id}{quality}{''.join(codecs)}{transport}"
    digest = hmac.new(FILE_INFO_SIGN_KEY, message.encode(), hashlib.sha256).digest()
    # Yandex expects the base64 signature without its last character
    return base64.b64encode(digest).decode()[:-1]


def cover_url(cover_uri: str) -> str:
    # Covers come as "avatars.yandex.net/get-music-content/.../%%", %% being the size
    url = cover_uri.replace("%%", "1000x1000")
    return url if "://" in url else f"https://{url}"


class YandexMusicIE(InfoExtractor):
    """
    Single Yandex Music tracks through the mobile API, with the bot's token passed as the
    extractor argument ``yandexmusic:token``. Stands in for yt-dlp's own Yandex Music
    extractors, whose web API no longer works.
    """

    IE_NAME = "yandexmusic"
    _VALID_URL = r"https?://music\.yandex\.[a-z]+/(?:album/\d+/)?track/(?P<id>\d+)"

    def _real_extract(self, url: str) -> dict[str, Any]:
        track_id = self._match_id(url)
        token = self._configuration_arg("token", [None], casesense=True)[0]
        if not token:
            raise ExtractorError("Not signed in to Yandex Music", expected=True)

        track = self._call_api(f"tracks/{track_id}", track_id, token, "Downloading track info")[0]
        if not track.get("available"):
            raise ExtractorError("This track isn't available on Yandex Music", expected=True)

        formats = {}
        # Yandex picks the codec from the ones asked for: AAC when the track has it, else MP3
        for codecs in (["aac-mp4", "mp3"], ["mp3"]):
            if "mp3" in formats:
                break
            file = self._file_info(track_id, token, codecs)
            if file.get("quality") == "preview":
                raise ExtractorError(
                    "Yandex Music only gives out a 30-second preview", expected=True
                )
            if file.get("codec") in FILE_CODECS and file.get("transport") == "raw":
                ext, acodec = FILE_CODECS[file["codec"]]
                formats[acodec] = {
                    "format_id": f"{file['codec']}-{file.get('bitrate')}",
                    "url": file.get("url") or file["urls"][0],
                    "ext": ext,
                    "acodec": acodec,
                    "vcodec": "none",
                    "abr": int_or_none(file.get("bitrate")),
                }
        if not formats:
            raise ExtractorError("Yandex Music has no usable file for this track")

        title = track["title"]
        if track.get("version"):
            title = f"{title} ({track['version']})"
        album = (track.get("albums") or [{}])[0]
        cover = track.get("coverUri") or album.get("coverUri")
        return {
            "id": track_id,
            "title": title,
            "track": title,
            "artists": [
                artist["name"] for artist in track.get("artists") or [] if artist.get("name")
            ],
            "album": album.get("title"),
            "release_year": int_or_none(album.get("year")),
            "duration": float_or_none(track.get("durationMs"), 1000),
            "thumbnail": cover_url(cover) if cover else None,
            "webpage_url": f"https://music.yandex.ru/track/{track_id}",
            "formats": list(formats.values()),
        }

    def _call_api(
        self,
        path: str,
        track_id: str,
        token: str,
        note: str,
        query: dict[str, Any] | None = None,
        client: str = MUSIC_CLIENT,
    ) -> Any:
        headers = {"Authorization": f"OAuth {token}", "X-Yandex-Music-Client": client}
        try:
            response = self._download_json(
                f"{API_URL}/{path}", track_id, note, query=query or {}, headers=headers
            )
        except ExtractorError as e:
            if isinstance(e.cause, HTTPError) and e.cause.status in (401, 403):
                raise ExtractorError(
                    "Yandex Music no longer accepts the bot's sign-in", expected=True
                ) from e
            raise
        return response["result"]

    def _file_info(self, track_id: str, token: str, codecs: list[str]) -> dict[str, Any]:
        """
        Where to download the track from, unencrypted, in one of ``codecs``.
        """
        timestamp = int(time.time())
        quality, transport = "lossless", "raw"
        query = {
            "ts": timestamp,
            "trackId": track_id,
            "quality": quality,
            "codecs": ",".join(codecs),
            "transports": transport,
            "sign": file_info_sign(timestamp, track_id, codecs, quality, transport),
        }
        result = self._call_api(
            "get-file-info", track_id, token, "Downloading file info", query, FILE_INFO_CLIENT
        )
        return result["downloadInfo"]
