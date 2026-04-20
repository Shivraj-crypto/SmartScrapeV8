from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _parse_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    navigation_timeout_ms: int = 45000
    wait_for_network_idle: bool = True
    headless: bool = True
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    @classmethod
    def from_env(cls) -> "Settings":
        # Load .env values only when settings are requested.
        load_dotenv()

        timeout_raw = os.getenv(
            "SCRAPE_NAVIGATION_TIMEOUT_MS", str(cls.navigation_timeout_ms)
        )
        try:
            timeout_ms = int(timeout_raw)
        except ValueError:
            timeout_ms = cls.navigation_timeout_ms

        if timeout_ms <= 0:
            timeout_ms = cls.navigation_timeout_ms

        gemini_model = os.getenv("GEMINI_MODEL", cls.gemini_model).strip()
        if not gemini_model:
            gemini_model = cls.gemini_model

        settings = cls(
            navigation_timeout_ms=timeout_ms,
            wait_for_network_idle=_parse_bool(
                os.getenv("SCRAPE_WAIT_FOR_NETWORK_IDLE"),
                default=True,
            ),
            headless=_parse_bool(
                os.getenv("SCRAPE_HEADLESS"),
                default=True,
            ),
            gemini_api_key=os.getenv("GEMINI_API_KEY"),
            gemini_model=gemini_model,
        )

        logger.debug(
            "settings_loaded",
            extra={
                "timeout_ms": settings.navigation_timeout_ms,
                "headless": settings.headless,
                "network_idle": settings.wait_for_network_idle,
                "gemini_model": settings.gemini_model,
                "has_api_key": bool(settings.gemini_api_key),
            },
        )
        return settings
