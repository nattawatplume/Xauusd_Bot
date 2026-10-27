"""Long-term Memory and Knowledge System for Cloud AI Trader."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from data.database import get_db_connection

log = logging.getLogger("ai_trader.memory")


class Memory:
    """Manages long-term storage, self-modifiable knowledge files, and trade databases."""

    def __init__(self) -> None:
        self.knowledge_dir = settings.KNOWLEDGE_DIR
        self.prompts_dir = settings.PROMPTS_DIR
        self.changelog_file = self.knowledge_dir / "changelog.jsonl"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Knowledge File Readers
    # -------------------------------------------------------------------------
    def get_trading_rules(self) -> str:
        path = self.knowledge_dir / "trading_rules.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_strategy_preferences(self) -> str:
        path = self.knowledge_dir / "strategy_preferences.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_market_insights(self) -> str:
        path = self.knowledge_dir / "market_insights.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def get_prompt(self, filename: str) -> str:
        path = self.prompts_dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else ""

    # -------------------------------------------------------------------------
    # Self-Modification Knowledge Updaters
    # -------------------------------------------------------------------------
    async def update_knowledge_file(
        self,
        filename: str,
        new_content: str,
        reason: str,
        triggered_by: str,
    ) -> None:
        """Update a knowledge file and record the version history to changelog and DB."""
        file_path = self.knowledge_dir / filename
        old_content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""

        # Write new content
        file_path.write_text(new_content, encoding="utf-8")
        log.info("Knowledge file %s updated by %s: %s", filename, triggered_by, reason)

        # Log change to changelog.jsonl
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "file": filename,
            "reason": reason,
            "triggered_by": triggered_by,
        }
        with self.changelog_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Record in database
        def _db_insert() -> None:
            with get_db_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO knowledge_changes (file_changed, change_type, old_content, new_content, reason, triggered_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (filename, "modify", old_content[:3000], new_content[:3000], reason, triggered_by),
                )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _db_insert)

    async def update_trading_rules(self, new_rules: str, reason: str, triggered_by: str = "ai_reflection") -> None:
        await self.update_knowledge_file("trading_rules.md", new_rules, reason, triggered_by)

    async def update_strategy_preferences(self, new_prefs: str, reason: str, triggered_by: str = "daily_review") -> None:
        await self.update_knowledge_file("strategy_preferences.md", new_prefs, reason, triggered_by)

    async def update_market_insights(self, new_insights: str, reason: str, triggered_by: str = "daily_review") -> None:
        await self.update_knowledge_file("market_insights.md", new_insights, reason, triggered_by)

    # -------------------------------------------------------------------------
    # Database Operations
    # -------------------------------------------------------------------------
    async def log_decision(self, decision_data: dict[str, Any]) -> int:
        """Persist a decision (and its shadow-tracking plan, if any) to SQLite."""
        plan = decision_data.get("shadow_plan") or {}

        def _insert() -> int:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO decisions (bar_time, action, confidence, regime, setup, stop_atr, target_r, reason,
                        was_executed, rejection_reason, ai_verdict, llm_model, candidate_side, candidate_setup,
                        signal_t, entry_ref, risk_price, target_r_plan, spread_price, outcome)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(decision_data.get("bar_time", "")),
                        str(decision_data.get("action", "NO_TRADE")),
                        float(decision_data.get("confidence", 0.0)),
                        str(decision_data.get("regime", "unclear")),
                        str(decision_data.get("setup", "none")),
                        float(decision_data.get("stop_atr", 1.5)),
                        float(decision_data.get("target_r", 1.5)),
                        str(decision_data.get("reason", ""))[:1000],
                        1 if decision_data.get("was_executed") else 0,
                        decision_data.get("rejection_reason"),
                        decision_data.get("ai_verdict"),
                        decision_data.get("llm_model"),
                        plan.get("candidate_side"),
                        plan.get("candidate_setup"),
                        plan.get("signal_t"),
                        plan.get("entry_ref"),
                        plan.get("risk_price"),
                        plan.get("target_r_plan"),
                        plan.get("spread_price"),
                        plan.get("outcome"),
                    ),
                )
                return cursor.lastrowid or 0

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _insert)

    async def log_trade_opened(self, trade_data: dict[str, Any]) -> int:
        """Record a broker-confirmed entry. The ticket is the MT5 position id."""
        def _upsert() -> int:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO trades (ticket, symbol, direction, entry_price, sl_price, tp_price, lot_size, open_time,
                        regime, setup, ai_confidence, ai_reason, risk_usd, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                    ON CONFLICT(ticket) DO UPDATE SET
                        entry_price = excluded.entry_price, sl_price = excluded.sl_price,
                        tp_price = excluded.tp_price, lot_size = excluded.lot_size,
                        open_time = excluded.open_time, risk_usd = excluded.risk_usd
                    """,
                    (
                        int(trade_data.get("ticket", 0)),
                        str(trade_data.get("symbol", "XAUUSD"))[:32],
                        str(trade_data.get("direction", "BUY")),
                        float(trade_data.get("entry_price", 0.0)),
                        float(trade_data.get("sl_price", 0.0)),
                        float(trade_data.get("tp_price", 0.0)),
                        float(trade_data.get("lot_size", 0.01)),
                        str(trade_data.get("open_time") or datetime.now(timezone.utc).isoformat())[:40],
                        str(trade_data.get("regime", "unclear"))[:40],
                        str(trade_data.get("setup", "none"))[:40],
                        float(trade_data.get("ai_confidence", 0.0)),
                        str(trade_data.get("ai_reason", ""))[:1000],
                        trade_data.get("risk_usd"),
                    ),
                )
                return cursor.lastrowid or 0

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _upsert)

    async def log_trade_closed(self, trade_data: dict[str, Any]) -> dict[str, Any]:
        """Close (or partially close) a position and compute its R multiple.

        A close for a position whose entry was never reported is still recorded
        so the ledger and performance stats stay complete.
        """
        ticket = int(trade_data.get("ticket", 0))

        def _update() -> dict[str, Any]:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                row = cursor.execute("SELECT * FROM trades WHERE ticket = ?", (ticket,)).fetchone()
                if row is None:
                    cursor.execute(
                        """
                        INSERT INTO trades (ticket, symbol, direction, entry_price, sl_price, tp_price, lot_size,
                            open_time, status)
                        VALUES (?, ?, ?, ?, 0, 0, ?, ?, 'open')
                        """,
                        (
                            ticket,
                            str(trade_data.get("symbol", "XAUUSD"))[:32],
                            str(trade_data.get("direction", "BUY")),
                            float(trade_data.get("entry_price", 0.0)),
                            float(trade_data.get("volume", 0.0)),
                            str(trade_data.get("open_time", ""))[:40],
                        ),
                    )
                    row = cursor.execute("SELECT * FROM trades WHERE ticket = ?", (ticket,)).fetchone()

                # "cumulative" closes carry the position's whole net P&L; others add a partial close.
                cumulative = bool(trade_data.get("cumulative"))
                prior_pnl = float(row["pnl_usd"] or 0.0) if row["status"] == "closed" and not cumulative else 0.0
                pnl_usd = prior_pnl + float(trade_data.get("pnl_usd", 0.0))
                risk = row["risk_usd"]
                pnl_r = round(pnl_usd / risk, 3) if risk and risk > 0 else None
                cursor.execute(
                    """
                    UPDATE trades
                    SET close_price = ?, pnl_usd = ?, pnl_r = ?, close_time = ?, hold_bars = ?, status = 'closed'
                    WHERE ticket = ?
                    """,
                    (
                        float(trade_data.get("close_price", 0.0)),
                        round(pnl_usd, 2),
                        pnl_r,
                        str(trade_data.get("close_time") or datetime.now(timezone.utc).isoformat())[:40],
                        int(trade_data.get("hold_bars", 0)),
                        ticket,
                    ),
                )
                return dict(cursor.execute("SELECT * FROM trades WHERE ticket = ?", (ticket,)).fetchone())

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _update)

    async def log_equity(self, t: int, balance: float | None, equity: float | None) -> None:
        def _insert() -> None:
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO equity_snapshots (t, balance, equity) VALUES (?, ?, ?)",
                    (t, balance, equity),
                )

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _insert)

    async def get_equity_curve(self, limit: int = 600) -> list[dict[str, Any]]:
        def _fetch() -> list[dict[str, Any]]:
            with get_db_connection() as conn:
                rows = conn.execute(
                    "SELECT t, balance, equity FROM equity_snapshots ORDER BY t DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in reversed(rows)]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch)

    async def log_reflection(self, reflection_data: dict[str, Any]) -> int:
        """Record post-trade reflection to database."""
        def _insert() -> int:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO reflections (trade_id, expected_outcome, actual_outcome, analysis, lessons_learned, suggested_changes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(reflection_data.get("trade_id", 0)),
                        str(reflection_data.get("expected_outcome", "")),
                        str(reflection_data.get("actual_outcome", "")),
                        str(reflection_data.get("analysis", "")),
                        str(reflection_data.get("key_lesson", "")),
                        json.dumps(
                            {
                                "rule": reflection_data.get("suggested_rule_change"),
                                "param": reflection_data.get("suggested_param_change"),
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
                return cursor.lastrowid or 0

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _insert)

    async def log_daily_review(self, review_data: dict[str, Any]) -> int:
        """Record daily review report."""
        def _insert() -> int:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO daily_reviews (date, trades_count, wins, losses, net_pnl_r, summary, rule_changes_applied, param_changes_applied)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(review_data.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))),
                        int(review_data.get("trades_count", 0)),
                        int(review_data.get("wins", 0)),
                        int(review_data.get("losses", 0)),
                        float(review_data.get("net_pnl_r", 0.0)),
                        str(review_data.get("summary", "")),
                        json.dumps(review_data.get("proposed_rule_changes", []), ensure_ascii=False),
                        json.dumps(review_data.get("proposed_param_changes", []), ensure_ascii=False),
                    ),
                )
                return cursor.lastrowid or 0

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _insert)

    async def get_recent_trades(self, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch recent trades."""
        def _fetch() -> list[dict[str, Any]]:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
                return [dict(row) for row in cursor.fetchall()]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch)

    async def get_recent_decisions(self, limit: int = 30) -> list[dict[str, Any]]:
        """Fetch recent decisions."""
        def _fetch() -> list[dict[str, Any]]:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))
                return [dict(row) for row in cursor.fetchall()]

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _fetch)

    async def get_performance_summary(self) -> dict[str, Any]:
        """Calculate overall trading performance."""
        def _calc() -> dict[str, Any]:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT pnl_usd, pnl_r FROM trades WHERE status = 'closed'")
                rows = cursor.fetchall()

            total = len(rows)
            if total == 0:
                return {
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "net_pnl_usd": 0.0,
                    "net_pnl_r": 0.0,
                    "profit_factor": 0.0,
                }

            wins = [r["pnl_usd"] for r in rows if (r["pnl_usd"] or 0) > 0]
            losses = [r["pnl_usd"] for r in rows if (r["pnl_usd"] or 0) < 0]
            win_sum = sum(wins)
            loss_sum = abs(sum(losses))
            net_usd = sum(r["pnl_usd"] or 0 for r in rows)
            net_r = sum(r["pnl_r"] or 0 for r in rows)

            return {
                "total_trades": total,
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round((len(wins) / total) * 100, 1),
                "net_pnl_usd": round(net_usd, 2),
                "net_pnl_r": round(net_r, 2),
                "profit_factor": round(win_sum / loss_sum, 2) if loss_sum > 0 else 999.0,
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _calc)
