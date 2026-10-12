from aiogram.methods import SendMessage
from aiogram.types import ChatMemberAdministrator, ChatMemberLeft, ChatShared, User

from musicbot.config import AudioFormat
from musicbot.db.models import User as DbUser
from musicbot.handlers.settings import SettingsCallback
from tests.conftest import CHANNEL_ID, USER_ID, Harness


async def stored_user(harness: Harness) -> DbUser:
    async with harness.database.session() as session:
        return await session.get(DbUser, USER_ID)


def bot_admin(can_post_messages: bool) -> ChatMemberAdministrator:
    return ChatMemberAdministrator(
        user=User(id=123456, is_bot=True, first_name="Bot"),
        can_be_edited=False,
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=False,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_send_welcome_messages=False,
        can_post_messages=can_post_messages,
    )


async def test_settings_show_defaults(allowed: Harness):
    calls = await allowed.send("/settings")
    message = calls.last("SendMessage")
    assert "M4A, original quality" in message.text
    assert "This chat" in message.text
    labels = [button.text for row in message.reply_markup.inline_keyboard for button in row]
    assert labels == ["✅ M4A", "MP3", "📢 Post to a channel"]


async def test_switch_format(allowed: Harness):
    calls = await allowed.press(SettingsCallback(action="format", value="mp3"))
    assert "MP3, plays everywhere" in calls.last("EditMessageText").text
    assert (await stored_user(allowed)).audio_format is AudioFormat.MP3


async def test_pressing_the_current_format_changes_nothing(allowed: Harness):
    calls = await allowed.press(SettingsCallback(action="format", value="m4a"))
    assert calls.names() == ["AnswerCallbackQuery"]


async def test_choose_a_channel(allowed: Harness):
    calls = await allowed.press(SettingsCallback(action="channel"))
    picker = calls.last("SendMessage").reply_markup.keyboard[0][0].request_chat
    assert picker.chat_is_channel and picker.bot_administrator_rights.can_post_messages

    allowed.session.responses["GetChatMember"] = bot_admin(can_post_messages=True)
    shared = ChatShared(request_id=picker.request_id, chat_id=CHANNEL_ID, title="Tunes")
    calls = await allowed.send(chat_shared=shared)

    replies = [call.text for call in calls.calls if isinstance(call, SendMessage)]
    assert "posted to <b>Tunes</b>" in replies[0]
    assert "📢 Tunes" in replies[1]
    user = await stored_user(allowed)
    assert (user.channel_id, user.channel_title) == (CHANNEL_ID, "Tunes")


async def test_channel_without_post_rights_is_refused(allowed: Harness):
    allowed.session.responses["GetChatMember"] = bot_admin(can_post_messages=False)
    calls = await allowed.send(chat_shared=ChatShared(request_id=1, chat_id=CHANNEL_ID))
    assert "can't post" in calls.last("SendMessage").text
    assert (await stored_user(allowed)).channel_id is None


async def test_channel_the_bot_is_not_in_is_refused(allowed: Harness):
    allowed.session.responses["GetChatMember"] = ChatMemberLeft(
        user=User(id=123456, is_bot=True, first_name="Bot")
    )
    calls = await allowed.send(chat_shared=ChatShared(request_id=1, chat_id=CHANNEL_ID))
    assert "can't post" in calls.last("SendMessage").text


async def test_send_here_instead(allowed: Harness):
    await allowed.set_channel()
    calls = await allowed.press(SettingsCallback(action="clear"))
    assert "This chat" in calls.last("EditMessageText").text
    assert (await stored_user(allowed)).channel_id is None


async def test_cancel_channel_picker(allowed: Harness):
    calls = await allowed.send("✖️ Cancel")
    assert calls.last("SendMessage").reply_markup.remove_keyboard
