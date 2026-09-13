import os
import zoneinfo
from urllib.parse import urlsplit
from dataclasses import dataclass

from dotenv import load_dotenv


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip() or default


def _integer(name: str) -> int:
    try:
        return int(_required(name))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _allowed_user_ids() -> frozenset[int]:
    raw = _optional('ALLOWED_USER_IDS')
    if not raw:
        return frozenset()
    try:
        values = frozenset(int(part.strip()) for part in raw.split(','))
        if any(value <= 0 for value in values):
            raise ValueError
        return values
    except ValueError as exc:
        raise RuntimeError('ALLOWED_USER_IDS must contain comma-separated positive integers') from exc


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    openai_api_key: str
    owner_user_id: int
    nutrition_model: str
    transcription_model: str
    timezone: str
    database_path: str
    response_language: str
    notion_token: str
    notion_database_id: str
    allowed_user_ids: frozenset[int] = frozenset()
    mini_app_url: str = ""
    mini_app_port: int = 8765


def load_settings(env_file: str | None = ".env") -> Settings:
    if env_file:
        load_dotenv(env_file, override=False)
    mini_app_url = _optional("MINI_APP_URL")
    if mini_app_url:
        parsed = urlsplit(mini_app_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RuntimeError("MINI_APP_URL must be an HTTPS URL without credentials, query or fragment")
    try:
        mini_app_port = int(_optional("MINI_APP_PORT", "8765"))
        if not 1024 <= mini_app_port <= 65535:
            raise ValueError
    except ValueError as exc:
        raise RuntimeError("MINI_APP_PORT must be between 1024 and 65535") from exc
    timezone = _optional("TIMEZONE", "UTC")
    try:
        zoneinfo.ZoneInfo(timezone)
    except zoneinfo.ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Invalid TIMEZONE: {timezone}") from exc
    return Settings(
        telegram_token=_required("TELEGRAM_TOKEN"),
        openai_api_key=_required("OPENAI_API_KEY"),
        owner_user_id=_integer("OWNER_USER_ID"),
        nutrition_model=_optional("OPENAI_NUTRITION_MODEL", "gpt-6-astra"),
        transcription_model=_optional("OPENAI_TRANSCRIPTION_MODEL", "whisper-1"),
        timezone=timezone,
        database_path=_optional("DATABASE_PATH", ".data/nutrition.db"),
        response_language=_optional("RESPONSE_LANGUAGE", "English"),
        notion_token=_optional("NOTION_TOKEN"),
        notion_database_id=_optional("NOTION_DATABASE_ID"),
        allowed_user_ids=_allowed_user_ids(),
        mini_app_url=mini_app_url,
        mini_app_port=mini_app_port,
    )
