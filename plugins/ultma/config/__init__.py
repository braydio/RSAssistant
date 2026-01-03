"""Configuration helpers for the ULT-MA plugin."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import dotenv

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = CONFIG_DIR / ".env"


def load_env() -> None:
    """Load plugin-specific environment variables."""

    env_file_override = os.getenv("ULTMA_ENV_FILE")
    if env_file_override:
        override_path = Path(env_file_override)
        if not override_path.is_absolute():
            override_path = (CONFIG_DIR / override_path).resolve()
        if override_path.exists():
            dotenv.load_dotenv(dotenv_path=override_path)
            logger.info("ULT-MA env loaded from ULTMA_ENV_FILE=%s", override_path)
        else:
            logger.warning(
                "ULTMA_ENV_FILE set to %s but file not found; using process env only.",
                override_path,
            )
        return

    if DEFAULT_ENV_PATH.exists():
        dotenv.load_dotenv(dotenv_path=DEFAULT_ENV_PATH)
        logger.info("ULT-MA env loaded from %s", DEFAULT_ENV_PATH)


load_env()


def _parse_trading_brokers(raw_value: str) -> list[str]:
    """Return an ordered list of broker identifiers for automated trading."""

    if not raw_value:
        return []
    return [broker.strip() for broker in raw_value.split(",") if broker.strip()]


ENABLE_AUTOMATED_TRADING = (
    os.getenv("ENABLE_AUTOMATED_TRADING", "false").strip().lower() == "true"
)
TRADING_ALLOW_EXTENDED_TREND = (
    os.getenv("TRADING_ALLOW_EXTENDED_TREND", "false").strip().lower() == "true"
)
TRADING_TREND_SAFEGUARD_ENABLED = (
    os.getenv("TRADING_TREND_SAFEGUARD_ENABLED", "true").strip().lower() == "true"
)
TRADING_LOGGING_ENABLED = (
    os.getenv("TRADING_LOGGING_ENABLED", "true").strip().lower() == "true"
)
TRADING_TRAILING_BUFFER = float(os.getenv("TRADING_TRAILING_BUFFER", "0.03"))
TRADING_PRICE_CHECK_INTERVAL_SECONDS = int(
    os.getenv("TRADING_PRICE_CHECK_INTERVAL_SECONDS", str(5 * 60))
)
TRADING_BROKERS = _parse_trading_brokers(os.getenv("TRADING_BROKERS", ""))
AUTO_RSA_BASE_URL = os.getenv("AUTO_RSA_BASE_URL", "")
AUTO_RSA_API_KEY = os.getenv("AUTO_RSA_API_KEY", "")

if TRADING_BROKERS:
    logger.info(
        "Configured %d trading broker(s) for ULT-MA sells: %s",
        len(TRADING_BROKERS),
        ", ".join(TRADING_BROKERS),
    )
else:
    logger.info("No trading brokers configured; ULT-MA sells target 'all'.")


__all__ = [
    "AUTO_RSA_API_KEY",
    "AUTO_RSA_BASE_URL",
    "ENABLE_AUTOMATED_TRADING",
    "TRADING_ALLOW_EXTENDED_TREND",
    "TRADING_BROKERS",
    "TRADING_LOGGING_ENABLED",
    "TRADING_PRICE_CHECK_INTERVAL_SECONDS",
    "TRADING_TRAILING_BUFFER",
    "TRADING_TREND_SAFEGUARD_ENABLED",
]
