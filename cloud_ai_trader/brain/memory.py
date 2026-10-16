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
        """Persist a decision to SQLite."""
        def _insert() -> int:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO decisions (bar_time, action, confidence, regime, setup, stop_atr, target_r, reason, was_executed, rejection_reason)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )
                return cursor.lastrowid or 0

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _insert)

    async def log_trade_opened(self, trade_data: dict[str, Any]) -> int:
        """Log a newly opened trade."""
        def _insert() -> int:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                open_dt = trade_data.get("open_time")
                open_str = open_dt.isoformat() if isinstance(open_dt, datetime) else str(open_dt or datetime.now(timezone.utc).isoformat())
                cursor.execute(
                    """
                    INSERT INTO trades (ticket, symbol, direction, entry_price, sl_price, tp_price, lot_size, open_time, regime, setup, ai_confidence, ai_reason, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                    """,
                    (
                        int(trade_data.get("ticket", 0)),
                        str(trade_data.get("symbol", "XAUUSD")),
                        str(trade_data.get("direction", "BUY")),
                        float(trade_data.get("entry_price", 0.0)),
                        float(trade_data.get("sl_price", 0.0)),
                        float(trade_data.get("tp_price", 0.0)),
                        float(trade_data.get("lot_size", 0.01)),
                        open_str,
                        str(trade_data.get("regime", "unclear")),
                        str(trade_data.get("setup", "none")),
                        float(trade_data.get("ai_confidence", 0.0)),
                        str(trade_data.get("ai_reason", ""))[:1000],
                    ),
                )
                return cursor.lastrowid or 0

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _insert)

    async def log_trade_closed(self, trade_data: dict[str, Any]) -> dict[str, Any]:
        """Update closed trade stats in database."""
        ticket = int(trade_data.get("ticket", 0))

        def _update() -> dict[str, Any]:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                close_dt = trade_data.get("close_time") or datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    """
                    UPDATE trades
                    SET close_price = ?, pnl_usd = ?, pnl_r = ?, close_time = ?, hold_bars = ?, status = 'closed'
                    WHERE ticket = ?
                    """,
                    (
                        float(trade_data.get("close_price", 0.0)),
                        float(trade_data.get("pnl_usd", 0.0)),
                        float(trade_data.get("pnl_r", 0.0)),
                        str(close_dt),
                        int(trade_data.get("hold_bars", 0)),
                        ticket,
                    ),
                )
                cursor.execute("SELECT * FROM trades WHERE ticket = ? ORDER BY id DESC LIMIT 1", (ticket,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return {
                    "id": 0,
                    "ticket": ticket,
                    "regime": "unclear",
                    "setup": "none",
                    "ai_reason": "",
                }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _update)

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
