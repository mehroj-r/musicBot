from aiogram.types import User as TelegramUser
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from musicbot.db.base import utcnow
from musicbot.db.models import User


async def upsert_user(session: AsyncSession, tg_user: TelegramUser) -> tuple[User, bool]:
    """
    Create the user or refresh their name, atomically.

    :return: The stored user and whether it was created by this call.
    """
    now = utcnow()
    profile = {
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
        "username": tg_user.username,
    }
    statement = (
        insert(User)
        .values(id=tg_user.id, created_at=now, updated_at=now, **profile)
        .on_conflict_do_update(index_elements=[User.id], set_={**profile, "updated_at": now})
        .returning(User)
    )
    user = (await session.scalars(statement, execution_options={"populate_existing": True})).one()
    await session.commit()

    # created_at only equals `now` when this statement inserted the row
    return user, user.created_at == now
