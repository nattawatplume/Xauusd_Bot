"""Master Orchestrator for Cloud AI Trader.

Implements the OBSERVE -> THINK -> DECIDE -> ACT -> REFLECT -> LEARN cycle.
"""
from __future__ import annotations

import logging
from typing import Any

from config import settings
from brain.decision_engine import DecisionEngine
from brain.llm_client import LLMClient
from brain.market_analyzer import MarketAnalyzer
from brain.memory import Memory
from brain.reflection_engine import ReflectionEngine

log = logging.getLogger("ai_trader.brain")


class AIBrain:
    """The central intelligence coordinating perception, decision-making, and self-learning."""

    def __init__(self) -> None:
        self.memory = Memory()
        self.llm = LLMClient()
        self.analyzer = MarketAnalyzer(self.llm, self.memory)
        self.decision_engine = DecisionEngine(self.llm, self.memory)
        self.reflection_engine = ReflectionEngine(self.llm, self.memory)

        # In-memory deduplication cache for bar decisions
        self._last_decisions: dict[str, dict[str, Any]] = {}

    async def process_bar(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Core cycle: OBSERVE -> THINK -> DECIDE."""
        symbol = str(snapshot.get("symbol", "XAUUSD"))
        bar_time = str(snapshot.get("bar_time", ""))
        cache_key = f"{symbol}:{bar_time}"

        # Deduplication: Avoid re-processing the same closed candle
        if cache_key in self._last_decisions:
            return self._last_decisions[cache_key]

        log.info("Processing bar %s for %s", bar_time, symbol)

        # 1. OBSERVE & THINK: Analyze market context
        market_context = await self.analyzer.analyze(snapshot)

        # 2. Extract account state
        account_state = {
            "equity": float(snapshot.get("equity", 100.0)),
            "balance": float(snapshot.get("balance", 100.0)),
            "open_position": str(snapshot.get("position", "none")),
        }

        # 3. DECIDE: Make reasoned trading decision
        decision = await self.decision_engine.decide(
            snapshot=snapshot,
            market_context=market_context,
            account_state=account_state,
        )

        decision["bar_time"] = bar_time
        decision["symbol"] = symbol
        decision["shadow_mode"] = settings.SHADOW_MODE

        # If shadow mode is active, prevent actual order placement
        if settings.SHADOW_MODE:
            decision["reason"] = f"[SHADOW MODE] {decision['reason']}"

        # 4. Record decision in memory & database
        try:
            await self.memory.log_decision(decision)
        except Exception as e:
            log.error("Failed to log decision to DB: %s", e)

        # Cache decision
        self._last_decisions[cache_key] = decision
        if len(self._last_decisions) > 100:
            oldest = list(self._last_decisions.keys())[0]
            del self._last_decisions[oldest]

        log.info(
            "Decision for %s: %s (conf: %.2f, regime: %s) - %s",
            bar_time,
            decision["action"],
            decision["confidence"],
            decision["regime"],
            decision["reason"],
        )
        return decision

    async def process_trade_closed(self, trade_result: dict[str, Any]) -> dict[str, Any]:
        """Core cycle: REFLECT -> LEARN."""
        log.info("Processing closed trade ticket #%s", trade_result.get("ticket"))

        # Update trade record in DB
        trade = await self.memory.log_trade_closed(trade_result)
        # Memory returns a plain dict, including a synthetic record when the
        # EA reports a close for a trade whose open event was not recorded.
        trade_id = int(trade.get("id", 0)) if trade else 0
        trade_result["trade_id"] = trade_id

        # Reflection
        original_decision = {
            "regime": trade.get("regime", "unclear") if trade else "unclear",
            "setup": trade.get("setup", "none") if trade else "none",
            "reason": trade.get("ai_reason", "") if trade else "",
        }

        reflection = await self.reflection_engine.reflect_on_trade(
            trade_result=trade_result,
            original_decision=original_decision,
        )
        return reflection

    async def run_daily_review(self) -> dict[str, Any]:
        """Conduct end-of-day reflection across all trades and decisions."""
        log.info("Starting daily AI trading review...")
        trades = await self.memory.get_recent_trades(limit=10)
        decisions = await self.memory.get_recent_decisions(limit=50)

        review = await self.reflection_engine.run_daily_review(
            trades_today=trades,
            decisions_today=decisions,
        )
        log.info("Daily review completed: %s", review.get("summary"))
        return review
