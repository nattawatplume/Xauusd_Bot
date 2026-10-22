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
        if adx >= 22.0:
            regime = "trending_up" if rsi > 50 else "trending_down"
            confidence = 0.75
        elif adx >= 16.0:
            regime = "trending_up" if rsi >= 50 else "trending_down"
            confidence = 0.60
        else:
            regime = "ranging"
            confidence = 0.65

        return {
            "regime": regime,
            "regime_confidence": confidence,
            "volatility": "normal",
            "news_risk": False,
            "summary": f"Heuristic: ADX={adx:.1f}, RSI={rsi:.1f}",
        }

    def _technical_candidates(self, snapshot: dict[str, Any]) -> list[dict[str, str]]:
        """Find a small set of closed-bar setups for the LLM to evaluate.

        Candidates are evidence only: they never place an order or override an
        explicit NO_TRADE decision. The EA remains responsible for execution
        and risk checks.
        """
        try:
            adx = float(snapshot.get("adx_m15", 0.0))
            atr = float(snapshot.get("atr_m5", 0.0))
            ema9 = float(snapshot.get("ema9_m5", 0.0))
            ema21 = float(snapshot.get("ema21_m5", 0.0))
            ema20_m15 = float(snapshot.get("ema20_m15", 0.0))
            ema50_m15 = float(snapshot.get("ema50_m15", 0.0))
            candles = snapshot.get("candles_m5", [])
            if not isinstance(candles, list) or len(candles) < 7 or atr <= 0:
                return []
            signal = candles[0]
            previous = candles[1]
            if not isinstance(signal, dict) or not isinstance(previous, dict):
                return []
            o = float(signal["o"])
            h = float(signal["h"])
            low = float(signal["l"])
            close = float(signal["c"])
            po = float(previous["o"])
            pc = float(previous["c"])
            if h <= low or ema9 <= 0 or ema21 <= 0 or ema20_m15 <= 0 or ema50_m15 <= 0:
                return []
        except (KeyError, TypeError, ValueError, OverflowError):
            return []

        body = abs(close - o)
        lower_wick = min(o, close) - low
        upper_wick = h - max(o, close)
        bullish_rejection = close > o and lower_wick >= max(body, atr * 0.05) and close >= low + 0.55 * (h - low)
        bearish_rejection = close < o and upper_wick >= max(body, atr * 0.05) and close <= h - 0.55 * (h - low)
        bullish_engulf = close > o and pc < po and close >= po and o <= pc
        bearish_engulf = close < o and pc > po and close <= po and o >= pc
        trend_up = ema20_m15 > ema50_m15 and adx >= 16.0
        trend_down = ema20_m15 < ema50_m15 and adx >= 16.0
        candidates: list[dict[str, str]] = []

        if trend_up and low <= max(ema9, ema21) + 0.35 * atr and close > ema9 and (bullish_rejection or bullish_engulf):
            candidates.append({"side": "BUY", "setup": "pullback", "evidence": "M15 EMA20>EMA50, ADX>=16; closed M5 candle retested EMA zone and closed with bullish rejection/engulfing."})
        if trend_down and h >= min(ema9, ema21) - 0.35 * atr and close < ema9 and (bearish_rejection or bearish_engulf):
            candidates.append({"side": "SELL", "setup": "pullback", "evidence": "M15 EMA20<EMA50, ADX>=16; closed M5 candle retested EMA zone and closed with bearish rejection/engulfing."})

        try:
            prior = candles[1:7]
            prior_high = max(float(c["h"]) for c in prior if isinstance(c, dict))
            prior_low = min(float(c["l"]) for c in prior if isinstance(c, dict))
            strong_bull_close = close > o and close >= h - 0.25 * (h - low)
            strong_bear_close = close < o and close <= low + 0.25 * (h - low)
            if trend_up and close > prior_high and strong_bull_close:
                candidates.append({"side": "BUY", "setup": "breakout", "evidence": "M15 trend aligned; closed M5 candle closed above the previous six closed-bar highs with a strong close."})
            if trend_down and close < prior_low and strong_bear_close:
                candidates.append({"side": "SELL", "setup": "breakout", "evidence": "M15 trend aligned; closed M5 candle closed below the previous six closed-bar lows with a strong close."})
        except (KeyError, TypeError, ValueError, OverflowError):
            pass

        return candidates

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
            "technical_candidates": self._technical_candidates(snapshot),
        }
