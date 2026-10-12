import pytest
from pydantic import ValidationError

from musicbot.config import MB, Settings, UploadMode
from tests.conftest import make_settings


def test_cloud_bot_api_by_default():
    settings = make_settings()
    assert settings.upload_mode is UploadMode.BOT_API
    assert settings.max_upload_size == 50 * MB


def test_telethon_when_api_credentials_are_set():
    settings = make_settings(api_id=1, api_hash="hash")
    assert settings.upload_mode is UploadMode.TELETHON
    assert settings.max_upload_size == 2000 * MB


def test_local_bot_api_server_wins_over_telethon():
    settings = make_settings(api_id=1, api_hash="hash", local_bot_api_url="http://bot-api:8081")
    assert settings.upload_mode is UploadMode.LOCAL_BOT_API
    assert settings.max_upload_size == 2000 * MB


def test_reads_existing_env_names(monkeypatch):
    # Names already used in deployed .env files keep working
    monkeypatch.setenv("BOT_API_TOKEN", "1:abc")
    monkeypatch.setenv("CHANNEL_ID", "-100123")
    monkeypatch.setenv("COOKIE_FILE", "secrets/cookies.txt")
    settings = Settings(_env_file=None)
    assert settings.bot_token.get_secret_value() == "1:abc"
    assert settings.channel_id == -100123
    assert str(settings.cookies_file) == "secrets/cookies.txt"


def test_missing_token_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("BOT_API_TOKEN", raising=False)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(ValidationError, match="BOT_API_TOKEN"):
        Settings(_env_file=None, channel_id=1)
