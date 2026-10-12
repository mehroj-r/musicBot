import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from musicbot.db.base import utcnow
from musicbot.db.database import Database
from musicbot.db.tokens import get_token, save_token
from musicbot.handlers import yandex as yandex_handlers
from musicbot.handlers.yandex import YandexCallback
from musicbot.services.yandex import (
    SERVICE,
    Account,
    DeviceCode,
    SignInStatus,
    YandexAuth,
    YandexError,
)
from tests.conftest import ADMIN_ID, Harness

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

        async def account_status(request: web.Request) -> web.Response:
            token = request.headers.get("Authorization", "").removeprefix("OAuth ")
            if token not in self.accounts:
                return web.json_response({"status": 401, "error": "Unauthorized"}, status=401)
            return web.json_response({"result": self.accounts[token]})

        app = web.Application()
        app.router.add_post("/device/code", device_code)
        app.router.add_post("/token", token)
        app.router.add_post("/revoke_token", revoke)
        app.router.add_get("/account/status", account_status)
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
