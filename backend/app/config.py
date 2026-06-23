"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Database ────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://netmon:netmon_secret@localhost:5432/netmon"

    # ── API ─────────────────────────────────────────────────────────
    api_port: int = 8000
    secret_key: str = "change_me_use_openssl_rand_hex_32"
    access_token_expire_minutes: int = 480  # 8 hours

    # ── Poller Intervals (seconds) ──────────────────────────────────
    snmp_poll_interval: int = 60
    esxi_poll_interval: int = 120

    # ── Telegram ────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── Email (SMTP) ────────────────────────────────────────────────
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_from_email: str = "netmon@local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
