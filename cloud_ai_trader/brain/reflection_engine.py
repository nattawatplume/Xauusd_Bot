"""Post-Trade Reflection and Self-Learning Engine for Cloud AI Trader."""
from __future__ import annotations

import json
import logging
from typing import Any

from config import settings
from brain.llm_client import LLMClient
from brain.memory import Memory

log = logging.getLogger("ai_trader.reflection")


class ReflectionEngine:
    """Reflects on trade results, discovers market patterns, and manages self-learning."""

    def __init__(self, llm: LLMClient, memory: Memory) -> None:
        self.llm = llm
        self.memory = memory

    async def reflect_on_trade(
        self,
        trade_result: dict[str, Any],
        original_decision: dict[str, Any],
    ) -> dict[str, Any]:
        """Deep post-mortem analysis of a closed trade."""
        system_prompt = self.memory.get_prompt("system_identity.md")
        reflection_prompt = self.memory.get_prompt("reflection.md")
        rules = self.memory.get_trading_rules()

        ai_reflection = await self.llm.reflect_on_trade(
            trade_result=trade_result,
            original_decision=original_decision,
            system_prompt=system_prompt,
            reflection_prompt=reflection_prompt,
            rules=rules,
        )

        pnl_usd = float(trade_result.get("pnl_usd", 0.0))
        expected = f"Expected profitable {original_decision.get('setup')} trade in {original_decision.get('regime')} market."
        pnl_r = trade_result.get("pnl_r")
        r_text = f"{float(pnl_r):.2f}R" if isinstance(pnl_r, (int, float)) else "R multiple unavailable"
        actual = f"Closed with PnL ${pnl_usd:.2f} ({r_text})."

        reflection_record = {
            "trade_id": trade_result.get("trade_id", 0),
            "expected_outcome": expected,
            "actual_outcome": actual,
            "analysis": ai_reflection.get("key_lesson", "Analyzed trade results."),
            "key_lesson": ai_reflection.get("key_lesson", ""),
            "suggested_rule_change": ai_reflection.get("suggested_rule_change"),
            "suggested_param_change": ai_reflection.get("suggested_param_change"),
        }

        # Store reflection in database
        await self.memory.log_reflection(reflection_record)

        # Append key lesson to market insights
        lesson = ai_reflection.get("key_lesson")
        if lesson and len(lesson) > 10:
            insights = self.memory.get_market_insights()
            updated_insights = f"{insights}\n- [{trade_result.get('close_time', 'Recently')}] {lesson}"
            await self.memory.update_market_insights(
                updated_insights,
                reason=f"Learned from Trade #{trade_result.get('ticket')}",
                triggered_by="post_trade_reflection",
            )

        return reflection_record

    async def run_daily_review(
        self,
        trades_today: list[dict[str, Any]],
        decisions_today: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Perform end-of-day synthesis across all decisions and trades."""
        system_prompt = self.memory.get_prompt("system_identity.md")
        review_prompt = self.memory.get_prompt("daily_review.md")
        rules = self.memory.get_trading_rules()
        prefs = self.memory.get_strategy_preferences()

        review = await self.llm.daily_review(
            trades_today=trades_today,
            decisions_today=decisions_today,
            system_prompt=system_prompt,
            daily_review_prompt=review_prompt,
            rules=rules,
            prefs=prefs,
        )

        wins = len([t for t in trades_today if (t.get("pnl_usd") or 0) > 0])
        losses = len([t for t in trades_today if (t.get("pnl_usd") or 0) < 0])
        net_r = sum(t.get("pnl_r") or 0 for t in trades_today)

        review_record = {
            "trades_count": len(trades_today),
            "wins": wins,
            "losses": losses,
            "net_pnl_r": round(net_r, 2),
            "summary": review.get("summary", "Daily review completed."),
            "proposed_rule_changes": review.get("proposed_rule_changes", []),
            "proposed_param_changes": review.get("proposed_param_changes", []),
        }

        await self.memory.log_daily_review(review_record)

        # Proposed changes are recorded for review only; no live rule or parameter
        # changes are applied without an explicit validation/approval workflow.
        for param_change in review.get("proposed_param_changes", []):
            param = param_change.get("param")
            val = param_change.get("proposed")
            if param == "SL_ATR_MULT" and isinstance(val, (int, float)):
                if settings.ADJUSTABLE_SL_ATR_MIN <= val <= settings.ADJUSTABLE_SL_ATR_MAX:
                    log.info("AI proposed SL_ATR_MULT %.2f for review: %s", val, param_change.get("reason"))
            elif param == "RR" and isinstance(val, (int, float)):
                if settings.ADJUSTABLE_RR_MIN <= val <= settings.ADJUSTABLE_RR_MAX:
                    log.info("AI proposed RR %.2f for review: %s", val, param_change.get("reason"))
            elif param == "CONFIDENCE_THRESHOLD" and isinstance(val, (int, float)):
                if settings.ADJUSTABLE_CONFIDENCE_MIN <= val <= settings.ADJUSTABLE_CONFIDENCE_MAX:
                    log.info("AI proposed CONFIDENCE_THRESHOLD %.2f for review: %s", val, param_change.get("reason"))

        return review_record
