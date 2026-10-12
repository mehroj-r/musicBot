from datetime import datetime

from sqlalchemy import BigInteger, Enum, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from musicbot.config import AudioFormat
from musicbot.db.base import Base, TimestampMixin, UTCDateTime


def audio_format_type() -> Enum:
    # Stored as the plain value ("m4a"), loaded back as AudioFormat
    return Enum(
        AudioFormat,
        native_enum=False,
        length=8,
        values_callable=lambda formats: [audio_format.value for audio_format in formats],
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Telegram user ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))

    # Access, granted by an admin
    is_allowed: Mapped[bool] = mapped_column(default=False, server_default=false())
    access_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # Preferences
    audio_format: Mapped[AudioFormat] = mapped_column(
        audio_format_type(),
        default=AudioFormat.M4A,
        server_default=AudioFormat.M4A.value,
    )
    # Channel the user's audio is posted to; their own chat when unset
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    channel_title: Mapped[str | None] = mapped_column(String(255))

    @property
    def display_name(self) -> str:
        name = " ".join(part for part in (self.first_name, self.last_name) if part)
        return name or str(self.id)


class CachedTrack(TimestampMixin, Base):
    """
    A track already uploaded once, so it can be sent again without downloading it.
    """

    __tablename__ = "cached_tracks"
    __table_args__ = (
        UniqueConstraint("source", "source_id", "audio_format", name="uq_cached_tracks_track"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # yt-dlp's extractor key and the ID it gives the track, e.g. "Youtube", "dQw4w9WgXcQ"
    source: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str] = mapped_column(String(255))
    audio_format: Mapped[AudioFormat] = mapped_column(audio_format_type())
    title: Mapped[str] = mapped_column(String(255))
    artist: Mapped[str] = mapped_column(String(255))

    # Bot API file ID, reusable in any chat; Telethon uploads don't produce one
    file_id: Mapped[str | None] = mapped_column(String(255))
    # The first post, copied when there is no file ID
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)


class OAuthToken(TimestampMixin, Base):
    """
    A token the bot signed in with, one per service.
    """

    __tablename__ = "oauth_tokens"

    # e.g. "yandex_music"
    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    access_token: Mapped[str] = mapped_column(String(1024))
    refresh_token: Mapped[str | None] = mapped_column(String(1024))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
