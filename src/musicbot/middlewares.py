from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TelegramUser

from musicbot.db.database import Database
from musicbot.db.users import upsert_user


class UserMiddleware(BaseMiddleware):
    """
    Registers every user who talks to the bot and passes them to handlers as
    ``db_user`` and ``is_new_user``.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TelegramUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        database: Database = data["database"]
        async with database.session() as session:
            data["db_user"], data["is_new_user"] = await upsert_user(session, tg_user)
        return await handler(event, data)
