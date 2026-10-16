"""SQLAlchemy models for Cloud AI Trader."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket: Mapped[int] = mapped_column(Integer, index=True)
    symbol: Mapped[str] = mapped_column(String(20), default="XAUUSD")
    direction: Mapped[str] = mapped_column(String(10))  # BUY / SELL
    entry_price: Mapped[float] = mapped_column(Float)
    sl_price: Mapped[float] = mapped_column(Float)
    tp_price: Mapped[float] = mapped_column(Float)
    close_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lot_size: Mapped[float] = mapped_column(Float, default=0.01)
    pnl_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_r: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    close_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hold_bars: Mapped[int] = mapped_column(Integer, default=0)
    regime: Mapped[str] = mapped_column(String(50), default="unclear")
    setup: Mapped[str] = mapped_column(String(50), default="none")
    ai_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ai_reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open / closed / cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    reflections: Mapped[list["Reflection"]] = relationship("Reflection", back_populates="trade")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    bar_time: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(20))  # BUY / SELL / NO_TRADE / EXIT
    confidence: Mapped[float] = mapped_column(Float)
    regime: Mapped[str] = mapped_column(String(50))
    setup: Mapped[str] = mapped_column(String(50))
    stop_atr: Mapped[float] = mapped_column(Float)
    target_r: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    was_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Reflection(Base):
    __tablename__ = "reflections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(Integer, ForeignKey("trades.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expected_outcome: Mapped[str] = mapped_column(Text)
    actual_outcome: Mapped[str] = mapped_column(Text)
    analysis: Mapped[str] = mapped_column(Text)
    lessons_learned: Mapped[str] = mapped_column(Text)
    suggested_changes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    trade: Mapped["Trade"] = relationship("Trade", back_populates="reflections")


class DailyReview(Base):
    __tablename__ = "daily_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[str] = mapped_column(String(20), index=True)
    trades_count: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    net_pnl_r: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str] = mapped_column(Text)
    rule_changes_applied: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    param_changes_applied: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgeChange(Base):
    __tablename__ = "knowledge_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    file_changed: Mapped[str] = mapped_column(String(100))
    change_type: Mapped[str] = mapped_column(String(20))  # add / modify / remove
    old_content: Mapped[str] = mapped_column(Text)
    new_content: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(String(50))  # reflection / daily_review / weekly_review
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
