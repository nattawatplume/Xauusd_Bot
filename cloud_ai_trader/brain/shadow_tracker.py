"""Shadow outcome tracking for Cloud AI Trader.

Every bar with a rule-based candidate is scored against the candles that follow
it, whether the AI approved it, rejected it, or was unavailable. Comparing the
"approved" and "rejected" groups is the only direct evidence of whether the LLM
filter adds value over the raw candidates.

Scoring mirrors the EA: entry at the decision-time ask/bid, stop = ATR x stop_atr
(at least SHADOW_MIN_RISK_ATR), target = stop x target_r, exit after max-hold bars.
A bar that touches both stop and target counts as a loss. MT5 candles are bid
prices, so short exits add the decision-time spread.
"""
from __future__ import annotations

import asyncio
import calendar
import logging
import math
from datetime import datetime
from typing import Any

from config import settings
from data.database import get_db_connection

log = logging.getLogger("ai_trader.shadow")

TRACKED_VERDICTS = ("approved", "rejected", "unavailable", "blocked")


def bar_epoch(bar_time: str) -> int | None:
    """MT5 'YYYY.MM.DD HH:MM' server time -> the same epoch MQL5 uses for datetime."""
    try:
        return calendar.timegm(datetime.strptime(bar_time[:16], "%Y.%m.%d %H:%M").timetuple())
    except ValueError:
        return None


def _num(snapshot: dict[str, Any], key: str) -> float | None:
    value = snapshot.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def build_plan(snapshot: dict[str, Any], decision: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Columns stored with a decision so it can be scored later. Empty when nothing to track."""
    if not candidates:
        return {}
    verdict = decision.get("ai_verdict") or "blocked"
    if verdict not in TRACKED_VERDICTS:
        return {}

    if verdict == "approved":
        side, setup = decision["action"], decision.get("setup", "none")
        stop_atr, target_r = float(decision["stop_atr"]), float(decision["target_r"])
    else:
        side, setup = candidates[0].get("side"), candidates[0].get("setup", "none")
        stop_atr, target_r = settings.SHADOW_DEFAULT_STOP_ATR, settings.SHADOW_DEFAULT_TARGET_R

    constraints = snapshot.get("constraints") if isinstance(snapshot.get("constraints"), dict) else {}
    min_risk_atr = _num(constraints, "min_risk_atr") or settings.SHADOW_MIN_RISK_ATR
    atr, bid, ask = _num(snapshot, "atr_m5"), _num(snapshot, "bid"), _num(snapshot, "ask")
    signal_t = bar_epoch(str(snapshot.get("bar_time", "")))
    if side not in {"BUY", "SELL"} or not atr or not bid or not ask or signal_t is None:
        return {}

    return {
        "candidate_side": side,
        "candidate_setup": setup,
        "signal_t": signal_t,
        "entry_ref": ask if side == "BUY" else bid,
        "risk_price": atr * max(stop_atr, min_risk_atr),
        "target_r_plan": target_r,
        "spread_price": max(0.0, ask - bid),
        "outcome": "pending",
    }


def _score(row: dict[str, Any], candles: list[dict[str, Any]], max_hold: int) -> tuple[str, float, int] | None:
    d = 1 if row["candidate_side"] == "BUY" else -1
    entry, risk, target_r = row["entry_ref"], row["risk_price"], row["target_r_plan"]
    spread = row["spread_price"] or 0.0
    if not risk or risk <= 0:
        return "expired", 0.0, 0
    sl, tp = entry - d * risk, entry + d * risk * target_r
    after = [c for c in candles if c["t"] > row["signal_t"]][:max_hold]
    for n, c in enumerate(after, start=1):
        s = spread if d < 0 else 0.0
        lo, hi = c["l"] + s, c["h"] + s
        if (lo <= sl) if d > 0 else (hi >= sl):
            return "loss", -1.0, n
        if (hi >= tp) if d > 0 else (lo <= tp):
            return "win", float(target_r), n
    if len(after) >= max_hold:
        exit_price = after[-1]["c"] + (spread if d < 0 else 0.0)
        return "timeout", round(d * (exit_price - entry) / risk, 3), len(after)
    if candles and candles[0]["t"] > row["signal_t"]:
        # The chart window no longer reaches back to the signal bar.
        return "expired", 0.0, len(after)
    return None


class ShadowTracker:
    """Resolves pending shadow outcomes and summarizes them for the dashboard."""

    async def resolve(self, candles: list[dict[str, Any]], max_hold: int | None = None) -> int:
        usable = sorted(
            (c for c in candles if all(isinstance(c.get(k), (int, float)) for k in ("t", "h", "l", "c"))),
            key=lambda c: c["t"],
        )
        if not usable:
            return 0
        hold = max_hold or settings.SHADOW_MAX_HOLD_BARS

        def _resolve() -> int:
            resolved = 0
            with get_db_connection() as conn:
                rows = conn.execute(
                    "SELECT id, candidate_side, signal_t, entry_ref, risk_price, target_r_plan, spread_price "
                    "FROM decisions WHERE outcome = 'pending'"
                ).fetchall()
                for row in rows:
                    result = _score(dict(row), usable, hold)
                    if result is None:
                        continue
                    outcome, r, bars = result
                    conn.execute(
                        "UPDATE decisions SET outcome = ?, outcome_r = ?, resolved_bars = ? WHERE id = ?",
                        (outcome, r, bars, row["id"]),
                    )
                    resolved += 1
            return resolved

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _resolve)

    async def summary(self) -> dict[str, Any]:
        def _calc() -> dict[str, Any]:
            with get_db_connection() as conn:
                rows = conn.execute(
                    "SELECT ai_verdict, outcome, outcome_r FROM decisions "
                    "WHERE outcome IS NOT NULL AND ai_verdict IS NOT NULL"
                ).fetchall()
            groups: dict[str, dict[str, Any]] = {}
            for name in ("all", *TRACKED_VERDICTS):
                groups[name] = {"n": 0, "pending": 0, "wins": 0, "net_r": 0.0}
            for row in rows:
                for name in ("all", row["ai_verdict"]):
                    g = groups.setdefault(name, {"n": 0, "pending": 0, "wins": 0, "net_r": 0.0})
                    if row["outcome"] == "pending":
                        g["pending"] += 1
                    elif row["outcome"] != "expired":
                        g["n"] += 1
                        g["wins"] += 1 if (row["outcome_r"] or 0) > 0 else 0
                        g["net_r"] += row["outcome_r"] or 0.0
            for g in groups.values():
                g["win_rate"] = round(g["wins"] / g["n"] * 100, 1) if g["n"] else None
                g["expectancy_r"] = round(g["net_r"] / g["n"], 3) if g["n"] else None
                g["net_r"] = round(g["net_r"], 2)
            return groups

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _calc)
