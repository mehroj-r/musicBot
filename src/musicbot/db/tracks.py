from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from musicbot.config import AudioFormat
from musicbot.db.base import utcnow
from musicbot.db.models import CachedTrack
from musicbot.services.downloader import Track
from musicbot.services.uploader import SentAudio


async def find_cached(
    session: AsyncSession, source: str, source_id: str, audio_format: AudioFormat
) -> CachedTrack | None:
    return await session.scalar(
        select(CachedTrack).where(
            CachedTrack.source == source,
            CachedTrack.source_id == source_id,
            CachedTrack.audio_format == audio_format,
        )
    )


async def save_cached(
    session: AsyncSession, track: Track, audio_format: AudioFormat, sent: SentAudio
) -> None:
    """
    Remember where the track was uploaded, replacing an older entry for it.
    """
    now = utcnow()
    location = {
        "title": track.title[:255],
        "artist": track.artist[:255],
        "file_id": sent.file_id,
        "chat_id": sent.chat_id,
        "message_id": sent.message_id,
    }
    statement = (
        insert(CachedTrack)
        .values(
            source=track.source,
            source_id=track.source_id,
            audio_format=audio_format,
            created_at=now,
            updated_at=now,
            **location,
        )
        .on_conflict_do_update(
            index_elements=["source", "source_id", "audio_format"],
            set_={**location, "updated_at": now},
        )
    )
    await session.execute(statement)
    await session.commit()


async def forget_cached(session: AsyncSession, cached_id: int) -> None:
    await session.execute(delete(CachedTrack).where(CachedTrack.id == cached_id))
    await session.commit()
