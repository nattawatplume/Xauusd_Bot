"""Configuration module for Cloud AI Trader.

Uses Pydantic BaseSettings for type-safe environment configuration,
hardcoded immutable guardrails, and flexible AI decision bounds.
"""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """System settings with environment variable overrides and trading guardrails."""

    # API Keys
    GEMINI_API_KEY: str = ""
    # Empty by default: the API refuses to start until a real secret is configured.
    BRIDGE_TOKEN: str = ""

    # Server
    # Bind locally by default. Put a TLS reverse proxy in front before remote access.
    HOST: str = "127.0.0.1"
    PORT: int = 8765

    # LLM
    LLM_MODEL: str = "gemini-3.6-flash"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_RETRIES: int = 3

    # Reference limits only. Live risk checks are currently enforced by the MT5 EA,
    # not independently by this proposal service.
    MAX_RISK_PCT: float = 5.0        # Max 5% risk per trade ($5 on $100)
    MAX_DAILY_LOSS_PCT: float = 8.0   # Stop trading if daily loss exceeds 8%
    MAX_DRAWDOWN_PCT: float = 15.0    # Circuit breaker
    MAX_TRADES_PER_DAY: int = 5       # Prevent overtrading
    MAX_SPREAD_POINTS: float = 40.0   # Reject entries above this broker-point spread

    # AI Decision Bounds (AI can adjust within these)
    MIN_CONFIDENCE: float = 0.65      # Minimum confidence to trade
    MIN_STOP_ATR: float = 0.5         # Minimum SL in ATR units
    MAX_STOP_ATR: float = 3.0         # Maximum SL in ATR units
    MIN_TARGET_R: float = 1.0         # Minimum R:R
    MAX_TARGET_R: float = 4.0         # Maximum R:R

    # AI Self-modification bounds
    ADJUSTABLE_SL_ATR_MIN: float = 0.5
    ADJUSTABLE_SL_ATR_MAX: float = 3.0
    ADJUSTABLE_RR_MIN: float = 1.0
    ADJUSTABLE_RR_MAX: float = 4.0
    ADJUSTABLE_CONFIDENCE_MIN: float = 0.5
    ADJUSTABLE_CONFIDENCE_MAX: float = 0.95

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent
    KNOWLEDGE_DIR: Path = BASE_DIR / "knowledge"
    PROMPTS_DIR: Path = BASE_DIR / "prompts"
    DB_URL: str = "sqlite+aiosqlite:///cloud_ai_trader/data/trader.db"

    # Scheduler
    DAILY_REVIEW_HOUR: int = 22       # UTC hour for daily review
    WEEKLY_REVIEW_DAY: int = 5        # Saturday (0=Mon, 5=Sat, 6=Sun in APScheduler standard)

    # Shadow mode
    SHADOW_MODE: bool = True          # Label proposals; the EA enforces no-order shadow mode
    ENABLE_TRADING: bool = False      # Status flag only; this service never sends broker orders

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
