from datetime import datetime

from sqlalchemy import BigInteger, Enum, String, false
from sqlalchemy.orm import Mapped, mapped_column

from musicbot.config import AudioFormat
from musicbot.db.base import Base, TimestampMixin, UTCDateTime


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
        Enum(
            AudioFormat,
            native_enum=False,
            length=8,
            values_callable=lambda formats: [audio_format.value for audio_format in formats],
        ),
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
