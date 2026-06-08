"""Configuration helpers for the outreach pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional before dependencies are installed
    def load_dotenv() -> bool:
        """Fallback no-op when python-dotenv is unavailable."""
        return False

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Settings:
    """Environment-backed application settings."""

    ocean_api_key: str = field(default_factory=lambda: os.getenv("OCEAN_API_KEY", ""))
    prospeo_api_key: str = field(default_factory=lambda: os.getenv("PROSPEO_API_KEY", ""))
    eazyreach_api_key: str = field(default_factory=lambda: os.getenv("EAZYREACH_API_KEY", ""))
    brevo_api_key: str = field(default_factory=lambda: os.getenv("BREVO_API_KEY", ""))
    brevo_sender_email: str = field(default_factory=lambda: os.getenv("BREVO_SENDER_EMAIL", ""))
    brevo_sender_name: str = field(default_factory=lambda: os.getenv("BREVO_SENDER_NAME", ""))
    fake_api_base_url: str = field(
        default_factory=lambda: os.getenv("FAKE_API_BASE_URL", "http://127.0.0.1:8000")
    )
    fake_api_fail_mode: str = field(default_factory=lambda: os.getenv("FAKE_API_FAIL_MODE", ""))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


def get_settings() -> Settings:
    """Return the loaded application settings."""
    return Settings()


def get_env_presence() -> dict[str, str]:
    """Return safe present/missing markers for submission checks."""
    settings = get_settings()
    return {
        "OCEAN_API_KEY": "present" if settings.ocean_api_key else "missing",
        "PROSPEO_API_KEY": "present" if settings.prospeo_api_key else "missing",
        "BREVO_API_KEY": "present" if settings.brevo_api_key else "missing",
        "BREVO_SENDER_EMAIL": "present" if settings.brevo_sender_email else "missing",
        "BREVO_SENDER_NAME": "present" if settings.brevo_sender_name else "missing",
    }
