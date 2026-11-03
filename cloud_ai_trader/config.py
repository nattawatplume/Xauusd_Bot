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
    PORT: int = 8766

    # LLM
    LLM_MODEL: str = "gemini-3.6-flash"
    # Used when the primary model is overloaded (HTTP 503) or slow.
    LLM_FALLBACK_MODEL: str = "gemini-3.5-flash-lite"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_RETRIES: int = 2
    LLM_TIMEOUT_S: float = 8.0
    # "low" roughly halves Gemini 3 latency; empty string uses the model default.
    LLM_THINKING_LEVEL: str = "low"
    # Ask the LLM about EXIT on every bar while a position is open. Off by default:
    # free-tier Gemini allows about 20 requests per model per day.
    LLM_REVIEW_OPEN_POSITIONS: bool = False
    # Whole decision must finish before the EA's AITimeoutMs (20 s default).
    DECISION_BUDGET_S: float = 15.0

    # Reference limits only. Live risk checks are currently enforced by the MT5 EA,
    # not independently by this proposal service.
    MAX_RISK_PCT: float = 5.0        # Max 5% risk per trade ($5 on $100)
    MAX_DAILY_LOSS_PCT: float = 8.0   # Stop trading if daily loss exceeds 8%
    MAX_DRAWDOWN_PCT: float = 15.0    # Circuit breaker
    MAX_TRADES_PER_DAY: int = 5       # Prevent overtrading
    MAX_SPREAD_POINTS: float = 40.0   # Reject entries above this broker-point spread

    # AI Decision Bounds (AI can adjust within these)
    MIN_CONFIDENCE: float = 0.50      # Balanced confidence floor for realistic trade capture
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

    # Shadow tracking: how candidate setups are scored when the AI did not set a plan.
    SHADOW_DEFAULT_STOP_ATR: float = 1.5
    SHADOW_DEFAULT_TARGET_R: float = 1.5
    SHADOW_MIN_RISK_ATR: float = 1.0  # mirrors the EA MinRiskATR input
    SHADOW_MAX_HOLD_BARS: int = 12    # mirrors the EA MaxHoldBars input

    # Live gate: AI-approved entries reach the broker only while the last
    # LIVE_GATE_WINDOW scored approvals (real and paper) average at least
    # LIVE_GATE_MIN_EXP_R. Otherwise the service keeps scoring them on paper.
    LIVE_GATE_ENABLED: bool = True
    LIVE_GATE_WINDOW: int = 20
    LIVE_GATE_MIN_EXP_R: float = 0.05

    # Shadow mode
    SHADOW_MODE: bool = True          # Label proposals; the EA enforces no-order shadow mode
    ENABLE_TRADING: bool = False      # Status flag only; this service never sends broker orders

    model_config = SettingsConfigDict(
        env_file=(Path(__file__).resolve().parent / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
