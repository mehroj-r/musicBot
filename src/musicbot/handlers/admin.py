import html

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject, Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from musicbot.access import AccessCallback, mention, notify_granted
from musicbot.config import Settings
from musicbot.db.database import Database
from musicbot.db.users import list_allowed, set_allowed

router = Router()


class IsAdmin(Filter):
    async def __call__(self, event: TelegramObject, is_admin: bool = False) -> bool:
        return is_admin


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def parse_user_id(args: str | None) -> int | None:
    try:
        return int((args or "").strip())
    except ValueError:
        return None


@router.message(Command("allow"))
async def allow_command(
    message: Message, command: CommandObject, database: Database, bot: Bot
) -> None:
    user_id = parse_user_id(command.args)
    if user_id is None:
        await message.reply("Usage: <code>/allow USER_ID</code>")
        return

    async with database.session() as session:
        user = await set_allowed(session, user_id, True)
    await message.reply(f"✅ {mention(user)} can now use the bot.")
    await notify_granted(bot, user_id)


@router.message(Command("revoke"))
async def revoke_command(
    message: Message, command: CommandObject, database: Database, settings: Settings
) -> None:
    user_id = parse_user_id(command.args)
    if user_id is None:
        await message.reply("Usage: <code>/revoke USER_ID</code>")
        return
    if user_id in settings.admin_ids:
        await message.reply("That's an admin from ADMIN_IDS; remove them there instead.")
        return

    async with database.session() as session:
        user = await set_allowed(session, user_id, False)
    await message.reply(f"🚫 {mention(user)} no longer has access.")


@router.message(Command("users"))
async def users_command(message: Message, database: Database, settings: Settings) -> None:
    async with database.session() as session:
        users = await list_allowed(session)

    admins = ", ".join(f"<code>{admin_id}</code>" for admin_id in settings.admin_ids)
    lines = ["👥 <b>Who can use the bot</b>", "", f"Admins: {admins}"]
    if users:
        lines += [f"• {mention(user)}: <code>{user.id}</code>" for user in users]
    else:
        lines.append("No one else yet. Use /allow USER_ID or the Allow button on a request.")
    await message.reply("\n".join(lines))


@router.callback_query(AccessCallback.filter())
async def access_decision(
    callback: CallbackQuery, callback_data: AccessCallback, database: Database, bot: Bot
) -> None:
    admin = html.escape(callback.from_user.first_name)
    if callback_data.action == "allow":
        async with database.session() as session:
            await set_allowed(session, callback_data.user_id, True)
        await notify_granted(bot, callback_data.user_id)
        outcome = f"✅ Allowed by {admin}"
    else:
        outcome = f"🚫 Ignored by {admin}"

    # Requests older than 48 hours can no longer be edited
    if isinstance(callback.message, Message):
        await callback.message.edit_text(f"{callback.message.html_text}\n\n{outcome}")
    await callback.answer()
