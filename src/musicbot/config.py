from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MB = 1024 * 1024


class AudioFormat(StrEnum):
    # AAC straight from YouTube: no re-encoding
    M4A = "m4a"
    MP3 = "mp3"

    @property
    def mime_type(self) -> str:
        return "audio/mp4" if self is AudioFormat.M4A else "audio/mpeg"


class UploadMode(StrEnum):
    # Cloud Bot API only: files up to 50 MB
    BOT_API = "bot_api"
    # Cloud Bot API, plus Telethon logged in as the bot for files above 50 MB
    TELETHON = "telethon"
    # Self-hosted Bot API server in --local mode: files up to 2000 MB
    LOCAL_BOT_API = "local_bot_api"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", validate_by_name=True)

    # Telegram
    bot_token: SecretStr = Field(validation_alias=AliasChoices("BOT_API_TOKEN", "BOT_TOKEN"))
    # Admins always have access and can grant it to others: ADMIN_IDS=111,222
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    api_id: int | None = None
    api_hash: SecretStr | None = None
    local_bot_api_url: str | None = None

    # Storage
    data_dir: Path = Path("data")
    cookies_file: Path | None = Field(
        default=None, validation_alias=AliasChoices("COOKIES_FILE", "COOKIE_FILE")
    )

    # Downloads
    max_parallel_downloads: int = Field(default=2, ge=1)
    max_duration_minutes: int = Field(default=180, ge=1)

    log_level: str = "INFO"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def split_admin_ids(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        return value

    @property
    def upload_mode(self) -> UploadMode:
        if self.local_bot_api_url:
            return UploadMode.LOCAL_BOT_API
        if self.api_id and self.api_hash:
            return UploadMode.TELETHON
        return UploadMode.BOT_API

    @property
    def max_upload_size(self) -> int:
        return 50 * MB if self.upload_mode == UploadMode.BOT_API else 2000 * MB

    @property
    def database_path(self) -> Path:
        return self.data_dir / "musicbot.db"
