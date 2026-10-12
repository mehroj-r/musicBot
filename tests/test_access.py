from aiogram.methods import AnswerCallbackQuery

from musicbot.access import AccessCallback
from musicbot.db.users import set_allowed
from musicbot.handlers.settings import SettingsCallback
from tests.conftest import ADMIN_ID, USER_ID, Harness

LINK = "https://youtu.be/pAgnJDJN4VA"


async def test_stranger_learns_their_id_and_admins_are_asked(harness: Harness):
    calls = await harness.send(LINK, first_name="Stranger")

    to_user = harness.calls_to(USER_ID)
    assert len(to_user) == 1
    assert f"<code>{USER_ID}</code>" in to_user[0].text
    assert harness.downloader.calls == []

    (request,) = harness.calls_to(ADMIN_ID)
    assert "Access request" in request.text
    buttons = [button.callback_data for button in request.reply_markup.inline_keyboard[0]]
    assert buttons == [
        AccessCallback(action="allow", user_id=USER_ID).pack(),
        AccessCallback(action="ignore", user_id=USER_ID).pack(),
    ]
    assert calls.names() == ["SendMessage", "SendMessage"]


async def test_admins_are_asked_once_a_day(harness: Harness):
    await harness.send("hello")
    await harness.send("hello again")
    assert harness.calls_to(ADMIN_ID) == []
    assert len(harness.calls_to(USER_ID)) == 1


async def test_without_admins_strangers_are_told_to_ask_the_owner(harness: Harness):
    harness.dispatcher.workflow_data["settings"].admin_ids.clear()
    try:
        calls = await harness.send("hello")
    finally:
        harness.dispatcher.workflow_data["settings"].admin_ids.append(ADMIN_ID)
    assert "ask its owner" in calls.last("SendMessage").text


async def test_strangers_in_groups_get_no_reply(harness: Harness):
    calls = await harness.send(LINK, chat_type="group")
    assert calls.calls == []


async def test_stranger_cannot_press_buttons(harness: Harness):
    calls = await harness.press(SettingsCallback(action="format", value="mp3"))
    answer = calls.last("AnswerCallbackQuery")
    assert isinstance(answer, AnswerCallbackQuery)
    assert answer.show_alert


async def test_admin_allows_from_the_request(harness: Harness):
    await harness.send("hello")

    calls = await harness.press(AccessCallback(action="allow", user_id=USER_ID), user_id=ADMIN_ID)

    assert "✅ You now have access" in harness.calls_to(USER_ID)[0].text
    edited = calls.last("EditMessageText").text
    # The request keeps its formatting, with the outcome added below
    assert edited == "<b>Old</b> text\n\n✅ Allowed by Presser"

    await harness.send(LINK)
    assert len(harness.downloader.calls) == 1


async def test_admin_ignores_a_request(harness: Harness):
    await harness.send("hello")
    calls = await harness.press(AccessCallback(action="ignore", user_id=USER_ID), user_id=ADMIN_ID)
    assert "Ignored by Presser" in calls.last("EditMessageText").text
    assert harness.calls_to(USER_ID) == []


async def test_allow_and_revoke_commands(harness: Harness):
    calls = await harness.send("/allow 555", user_id=ADMIN_ID)
    assert "can now use the bot" in harness.calls_to(ADMIN_ID)[0].text
    assert "✅ You now have access" in harness.calls_to(555)[0].text

    calls = await harness.send("/users", user_id=ADMIN_ID)
    assert "<code>555</code>" in calls.last("SendMessage").text

    calls = await harness.send("/revoke 555", user_id=ADMIN_ID)
    assert "no longer has access" in calls.last("SendMessage").text
    calls = await harness.send("/users", user_id=ADMIN_ID)
    assert "<code>555</code>" not in calls.last("SendMessage").text.split("Admins:")[1]


async def test_admins_from_config_cannot_be_revoked(harness: Harness):
    calls = await harness.send(f"/revoke {ADMIN_ID}", user_id=ADMIN_ID)
    assert "ADMIN_IDS" in calls.last("SendMessage").text


async def test_allow_needs_a_numeric_id(harness: Harness):
    calls = await harness.send("/allow someone", user_id=ADMIN_ID)
    assert "Usage" in calls.last("SendMessage").text


async def test_allowed_users_cannot_use_admin_commands(harness: Harness):
    async with harness.database.session() as session:
        await set_allowed(session, USER_ID, True)

    await harness.send("/allow 555")

    assert harness.calls_to(555) == []
    async with harness.database.session() as session:
        from musicbot.db.models import User

        assert await session.get(User, 555) is None
