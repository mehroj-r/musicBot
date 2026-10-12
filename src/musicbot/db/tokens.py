from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from musicbot.db.base import utcnow
from musicbot.db.models import OAuthToken


async def get_token(session: AsyncSession, service: str) -> OAuthToken | None:
    return await session.get(OAuthToken, service)


async def save_token(
    session: AsyncSession,
    service: str,
    access_token: str,
    refresh_token: str | None,
    expires_at: datetime | None,
) -> None:
    """
    Store the service's token, replacing the previous one.
    """
    now = utcnow()
    values = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
    }
    statement = (
        insert(OAuthToken)
        .values(service=service, created_at=now, updated_at=now, **values)
        .on_conflict_do_update(index_elements=["service"], set_={**values, "updated_at": now})
    )
    await session.execute(statement)
    await session.commit()


async def delete_token(session: AsyncSession, service: str) -> None:
    await session.execute(delete(OAuthToken).where(OAuthToken.service == service))
    await session.commit()
