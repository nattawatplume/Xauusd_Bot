"""Trade Decision Engine for Cloud AI Trader."""
from __future__ import annotations

import logging
import math
from typing import Any

from config import settings
from brain.llm_client import LLMClient
from brain.memory import Memory

log = logging.getLogger("ai_trader.decision")


class DecisionEngine:
    """Makes trade decisions by synthesizing market context, trading rules, and hard guardrails."""

    def __init__(self, llm: LLMClient, memory: Memory) -> None:
        self.llm = llm
        self.memory = memory

    async def decide(
        self,
        snapshot: dict[str, Any],
        market_context: dict[str, Any],
        account_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Make a reasoned trade decision with strict guardrail validation."""
        regime = market_context.get("regime", "unclear")
        news_risk = market_context.get("news_risk", False)
        volatility = market_context.get("volatility", "normal")
        spread = float(snapshot.get("spread_points", 0.0))
        position = str(snapshot.get("position", "none"))

        # ---------------------------------------------------------------------
        # Pre-Decision Hard Guardrails (Immediate NO_TRADE)
        # ---------------------------------------------------------------------
        if news_risk or volatility in {"high", "extreme"}:
            return {
                "action": "NO_TRADE",
                "confidence": 0.0,
                "regime": regime,
                "setup": "none",
                "stop_atr": settings.MIN_STOP_ATR,
                "target_r": settings.MIN_TARGET_R,
                "reason": "Hard Guardrail: High news risk or extreme market volatility.",
            }

        if not math.isfinite(spread) or spread < 0 or spread > settings.MAX_SPREAD_POINTS:
            return {
                "action": "NO_TRADE",
                "confidence": 0.0,
                "regime": regime,
                "setup": "none",
                "stop_atr": settings.MIN_STOP_ATR,
                "target_r": settings.MIN_TARGET_R,
                "reason": f"Hard Guardrail: spread {spread!r} is invalid or exceeds {settings.MAX_SPREAD_POINTS:.1f} points.",
            }

        if regime not in {"trending_up", "trending_down", "ranging", "breakout"}:
            return {
                "action": "NO_TRADE",
                "confidence": 0.0,
                "regime": regime,
                "setup": "none",
                "stop_atr": settings.MIN_STOP_ATR,
                "target_r": settings.MIN_TARGET_R,
                "reason": "Hard Guardrail: market regime is not classified well enough to enter.",
            }

        # ---------------------------------------------------------------------
        # Call LLM for Cognitive Decision
        # ---------------------------------------------------------------------
        system_prompt = self.memory.get_prompt("system_identity.md")
        decision_prompt = self.memory.get_prompt("trade_decision.md")
        rules = self.memory.get_trading_rules()
        prefs = self.memory.get_strategy_preferences()
        recent_trades = await self.memory.get_recent_trades(limit=5)

        ai_res = await self.llm.make_decision(
            market_context=market_context,
            system_prompt=system_prompt,
            decision_prompt=decision_prompt,
            rules=rules,
            prefs=prefs,
            recent_trades=recent_trades,
            account_state=account_state,
        )

        action = str(ai_res.get("action", "NO_TRADE")).upper()
        if action not in {"BUY", "SELL", "NO_TRADE", "EXIT"}:
            action = "NO_TRADE"

        try:
            confidence = float(ai_res.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        if not math.isfinite(confidence):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        setup = str(ai_res.get("setup", "none"))
        reason = str(ai_res.get("reason", "No reason provided."))

        # Stop and target bounded by immutable guardrails
        try:
            raw_stop = float(ai_res.get("stop_atr", 1.5))
        except (TypeError, ValueError):
            raw_stop = settings.MIN_STOP_ATR
        if not math.isfinite(raw_stop):
            raw_stop = settings.MIN_STOP_ATR
        stop_atr = max(settings.MIN_STOP_ATR, min(settings.MAX_STOP_ATR, raw_stop))

        try:
            raw_target = float(ai_res.get("target_r", 1.5))
        except (TypeError, ValueError):
            raw_target = settings.MIN_TARGET_R
        if not math.isfinite(raw_target):
            raw_target = settings.MIN_TARGET_R
        target_r = max(settings.MIN_TARGET_R, min(settings.MAX_TARGET_R, raw_target))

        # ---------------------------------------------------------------------
        # Position & Confidence Logic
        # ---------------------------------------------------------------------
        if position == "none" and action == "EXIT":
            action = "NO_TRADE"
            reason = "Ignored EXIT: No open position."

        if position != "none" and action in {"BUY", "SELL"}:
            action = "NO_TRADE"
            reason = "Ignored entry: An existing position is already open."

        if action in {"BUY", "SELL"} and confidence < settings.MIN_CONFIDENCE:
            action = "NO_TRADE"
            setup = "none"
            reason = f"Confidence {confidence:.2f} is below required threshold {settings.MIN_CONFIDENCE:.2f}."

        if action in {"NO_TRADE", "EXIT"}:
            setup = "none"

        return {
            "action": action,
            "confidence": confidence,
            "regime": regime,
            "setup": setup,
            "stop_atr": round(stop_atr, 2),
            "target_r": round(target_r, 2),
            "reason": reason[:200],
        }
