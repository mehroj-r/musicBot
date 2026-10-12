from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from musicbot.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Telegram user ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))
