from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.types import User as TelegramUser

from musicbot.access import REQUEST_COOLDOWN, notify_admins
from musicbot.config import Settings
from musicbot.db.database import Database
from musicbot.db.models import User
from musicbot.db.users import claim_access_request, upsert_user

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class UserMiddleware(BaseMiddleware):
    """
    Registers every user who talks to the bot and passes them to handlers as
    ``db_user`` and ``is_new_user``.
    """

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user: TelegramUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        database: Database = data["database"]
        async with database.session() as session:
            data["db_user"], data["is_new_user"] = await upsert_user(session, tg_user)
        return await handler(event, data)


class AccessMiddleware(BaseMiddleware):
    """
    Lets admins and allowed users through, passing ``is_admin`` to handlers. Everyone else
    learns their user ID, and the admins are asked whether to let them in.
    """

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: User | None = data.get("db_user")
        if user is None:
            return await handler(event, data)

        settings: Settings = data["settings"]
        is_admin = user.id in settings.admin_ids
        if is_admin or user.is_allowed:
            data["is_admin"] = is_admin
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("You don't have access to this bot.", show_alert=True)
        elif isinstance(event, Message) and event.chat.type == "private":
            await self.request_access(event, user, data)
        return None

    async def request_access(self, message: Message, user: User, data: dict[str, Any]) -> None:
        settings: Settings = data["settings"]
        if not settings.admin_ids:
            await message.answer(
                f"🔒 This bot is private. Your user ID is <code>{user.id}</code>; "
                "ask its owner for access."
            )
            return

        await message.answer(
            f"🔒 This bot is private. Your user ID is <code>{user.id}</code>.\n\n"
            "I've asked the admins to let you in; you'll get a message here once they do."
        )
        database: Database = data["database"]
        async with database.session() as session:
            should_notify = await claim_access_request(session, user.id, REQUEST_COOLDOWN)
        if should_notify:
            await notify_admins(data["bot"], settings.admin_ids, user)
