"""Built-in SQLite database setup for Cloud AI Trader.

Uses standard Python sqlite3 with async executors for maximum stability
and zero external database dependencies.
"""
from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from config import settings

db_path = settings.BASE_DIR / "data" / "trader.db"
db_path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional sqlite3 connection."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db_sync() -> None:
    """Initialize SQLite database tables using native DDL."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Trades table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket INTEGER NOT NULL,
                symbol TEXT DEFAULT 'XAUUSD',
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                close_price REAL,
                lot_size REAL DEFAULT 0.01,
                pnl_usd REAL,
                pnl_r REAL,
                open_time TEXT NOT NULL,
                close_time TEXT,
                hold_bars INTEGER DEFAULT 0,
                regime TEXT DEFAULT 'unclear',
                setup TEXT DEFAULT 'none',
                ai_confidence REAL DEFAULT 0.0,
                ai_reason TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Decisions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                bar_time TEXT NOT NULL,
                action TEXT NOT NULL,
                confidence REAL NOT NULL,
                regime TEXT NOT NULL,
                setup TEXT NOT NULL,
                stop_atr REAL NOT NULL,
                target_r REAL NOT NULL,
                reason TEXT NOT NULL,
                was_executed INTEGER DEFAULT 0,
                rejection_reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Reflections table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                expected_outcome TEXT,
                actual_outcome TEXT,
                analysis TEXT,
                lessons_learned TEXT,
                suggested_changes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Daily reviews table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                trades_count INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                net_pnl_r REAL DEFAULT 0.0,
                summary TEXT,
                rule_changes_applied TEXT,
                param_changes_applied TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Knowledge changes table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                file_changed TEXT NOT NULL,
                change_type TEXT NOT NULL,
                old_content TEXT,
                new_content TEXT,
                reason TEXT,
                triggered_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


async def init_db() -> None:
    """Async wrapper for initializing tables."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, init_db_sync)
