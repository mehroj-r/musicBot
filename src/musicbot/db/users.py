from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from aiogram.types import User as TelegramUser
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from musicbot.db.base import utcnow
from musicbot.db.models import User


async def upsert_user(session: AsyncSession, tg_user: TelegramUser) -> tuple[User, bool]:
    """
    Create the user or refresh their name.

    :return: The stored user and whether this is their first contact with the bot.
    """
    # Rows created by an admin's /allow have no name until the user first writes
    known_name = await session.scalar(select(User.first_name).where(User.id == tg_user.id))

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
    return user, not known_name


async def set_allowed(session: AsyncSession, user_id: int, allowed: bool) -> User:
    """
    Grant or revoke access. Works for users who never messaged the bot yet: their
    name is filled in once they do.
    """
    now = utcnow()
    statement = (
        insert(User)
        .values(id=user_id, first_name="", is_allowed=allowed, created_at=now, updated_at=now)
        .on_conflict_do_update(
            index_elements=[User.id], set_={"is_allowed": allowed, "updated_at": now}
        )
        .returning(User)
    )
    user = (await session.scalars(statement, execution_options={"populate_existing": True})).one()
    await session.commit()
    return user


async def update_user(session: AsyncSession, user_id: int, **values: Any) -> User:
    statement = (
        update(User).where(User.id == user_id).values(**values, updated_at=utcnow()).returning(User)
    )
    user = (await session.scalars(statement, execution_options={"populate_existing": True})).one()
    await session.commit()
    return user


async def list_allowed(session: AsyncSession) -> Sequence[User]:
    return (await session.scalars(select(User).where(User.is_allowed).order_by(User.id))).all()


async def claim_access_request(session: AsyncSession, user_id: int, cooldown: timedelta) -> bool:
    """
    Record an access request; True when admins should hear about it, at most once per cooldown.
    """
    now = utcnow()
    statement = (
        update(User)
        .where(User.id == user_id)
        .where((User.access_requested_at.is_(None)) | (User.access_requested_at < now - cooldown))
        .values(access_requested_at=now)
    )
    claimed = (await session.execute(statement)).rowcount == 1
    await session.commit()
    return claimed
