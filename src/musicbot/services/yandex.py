import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import aiohttp

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
