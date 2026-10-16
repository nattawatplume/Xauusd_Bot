"""Market Regime Analyzer for Cloud AI Trader."""
from __future__ import annotations

import logging
from typing import Any

from brain.llm_client import LLMClient
from brain.memory import Memory

log = logging.getLogger("ai_trader.analyzer")


class MarketAnalyzer:
    """Analyzes market conditions, volatility, news risk, and classifies market regimes."""

    def __init__(self, llm: LLMClient, memory: Memory) -> None:
        self.llm = llm
        self.memory = memory

    def _heuristic_regime(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Algorithmic baseline analysis used as anchor or fallback."""
        adx = float(snapshot.get("adx_m15", 0.0))
        rsi = float(snapshot.get("rsi_m5", 50.0))
        spread = float(snapshot.get("spread_points", 0.0))
        atr_m5 = float(snapshot.get("atr_m5", 0.0))

        # Check high volatility or wide spread
        if spread > 40.0:
            return {
                "regime": "high_volatility",
                "regime_confidence": 0.8,
                "volatility": "high",
                "news_risk": True,
                "summary": f"High spread ({spread:.1f} pts) - possible news or illiquid market.",
            }

        # Trend vs Range heuristics
        if adx >= 25.0:
            regime = "trending_up" if rsi > 50 else "trending_down"
            confidence = 0.75
        elif adx < 18.0:
            regime = "ranging"
            confidence = 0.70
        else:
            regime = "unclear"
            confidence = 0.50

        return {
            "regime": regime,
            "regime_confidence": confidence,
            "volatility": "normal",
            "news_risk": False,
            "summary": f"Heuristic: ADX={adx:.1f}, RSI={rsi:.1f}",
        }

    async def analyze(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Run deep AI market analysis using LLM + historical market insights."""
        system_prompt = self.memory.get_prompt("system_identity.md")
        analysis_prompt = self.memory.get_prompt("market_analysis.md")
        insights = self.memory.get_market_insights()

        heuristic = self._heuristic_regime(snapshot)

        # Call LLM for cognitive reasoning
        ai_analysis = await self.llm.analyze_market(
            snapshot=snapshot,
            system_prompt=system_prompt,
            analysis_prompt=analysis_prompt,
            market_insights=insights,
        )

        # Merge results with safety checks
        regime = ai_analysis.get("regime") or heuristic["regime"]
        valid_regimes = {
            "trending_up",
            "trending_down",
            "ranging",
            "breakout",
            "high_volatility",
            "pre_news",
            "unclear",
        }
        if regime not in valid_regimes:
            regime = heuristic["regime"]

        return {
            "regime": regime,
            "regime_confidence": float(ai_analysis.get("regime_confidence", heuristic["regime_confidence"])),
            "key_levels": ai_analysis.get("key_levels", {"support": [], "resistance": []}),
            "volatility": ai_analysis.get("volatility", heuristic["volatility"]),
            "news_risk": bool(ai_analysis.get("news_risk", heuristic["news_risk"])),
            "summary": str(ai_analysis.get("summary", heuristic["summary"])),
        }
