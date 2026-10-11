"""Application config — read from .env (pydantic-settings).

.env is looked up by ABSOLUTE path (project root), not relative to cwd — so that the MCP
server, launched by an MCP client from an arbitrary directory, picks up the right
password and port.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    database_url: str = "postgresql+psycopg://health:change_me_in_env@localhost:5432/health_os"
    # Separate read-only connection for MCP reads (role health_readonly, SELECT on views only).
    # Empty → fallback to database_url (so tests/dev work without the role configured).
    readonly_database_url: str = ""
    readonly_db_password: str = ""
    anthropic_api_key: str = ""
    alert_telegram_bot_token: str = ""
    alert_telegram_chat_id: str = ""
    # ISO country code for crisis hotlines in safety/crisis.py (default UA).
    crisis_country: str = "UA"


settings = Settings()
