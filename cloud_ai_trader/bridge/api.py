"""FastAPI Bridge Server connecting MetaTrader 5 and the Cloud AI Brain."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import settings
from brain.llm_client import quota_wait_s
from brain.orchestrator import AIBrain
from brain.shadow_tracker import bar_epoch
from data.database import init_db

log = logging.getLogger("ai_trader.api")

app = FastAPI(
    title="XAU Cloud AI Trader Bridge",
    description="Bridge connecting MT5 terminal to the autonomous Cloud AI trading brain.",
    version="2.0.0",
)

templates_dir = settings.BASE_DIR / "dashboard" / "templates"
templates = Jinja2Templates(directory=str(templates_dir)) if templates_dir.exists() else None

brain: AIBrain | None = None
latest_market_state: dict[str, Any] | None = None


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _positions_from_payload(raw_positions: Any, expected_symbol: str | None = None) -> list[dict[str, Any]]:
    """Keep only complete, numeric position facts reported by the MT5 EA."""
    if not isinstance(raw_positions, list) or len(raw_positions) > 20:
        raise HTTPException(status_code=400, detail="positions must be a list with at most 20 items")

    positions: list[dict[str, Any]] = []
    for item in raw_positions:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="invalid position item")
        direction = str(item.get("direction", "")).upper()
        numeric_fields = ("ticket", "volume", "entry_price", "sl_price", "tp_price", "profit")
        if direction not in {"BUY", "SELL"} or any(not _finite_number(item.get(key)) for key in numeric_fields):
            raise HTTPException(status_code=400, detail="position is missing valid broker values")
        item_symbol = str(item.get("symbol", ""))[:32]
        if (expected_symbol and item_symbol != expected_symbol) or not float(item["ticket"]).is_integer() or int(item["ticket"]) <= 0 or float(item["volume"]) <= 0:
            raise HTTPException(status_code=400, detail="position symbol, ticket, or volume is invalid")
        if float(item["entry_price"]) <= 0 or float(item["sl_price"]) < 0 or float(item["tp_price"]) < 0:
            raise HTTPException(status_code=400, detail="position prices are invalid")
        positions.append({
            "ticket": int(item["ticket"]),
            "symbol": item_symbol,
            "direction": direction,
            "volume": float(item["volume"]),
            "entry_price": float(item["entry_price"]),
            "sl_price": float(item["sl_price"]),
            "tp_price": float(item["tp_price"]),
            "profit": float(item["profit"]),
            "open_time": str(item.get("open_time", ""))[:40],
        })
    return positions


def _record_market_snapshot(snapshot: dict[str, Any]) -> None:
    """Retain only the latest source data needed by the read-only dashboard."""
    global latest_market_state
    raw_candles = snapshot.get("chart_candles_m5")
    chart_source = "chart_candles_m5"
    if not isinstance(raw_candles, list):
        raw_candles = snapshot.get("candles_m5")
        chart_source = "candles_m5"

    candles: list[dict[str, Any]] = []
    if isinstance(raw_candles, list):
        for candle in raw_candles[:120]:
            if not isinstance(candle, dict) or any(not _finite_number(candle.get(key)) for key in ("o", "h", "l", "c")):
                continue
            item = {key: float(candle[key]) for key in ("o", "h", "l", "c")}
            if isinstance(candle.get("label"), str):
                item["label"] = candle["label"][:32]
            if _finite_number(candle.get("t")):
                item["t"] = int(candle["t"])
            if _finite_number(candle.get("tv")):
                item["tv"] = int(candle["tv"])
            candles.append(item)

    positions_available = isinstance(snapshot.get("open_positions"), list)
    positions = _positions_from_payload(snapshot["open_positions"], str(snapshot.get("symbol", ""))) if positions_available else None
    state = {
        "available": True,
        "market_received_at": datetime.now(timezone.utc).isoformat(),
        "positions_received_at": datetime.now(timezone.utc).isoformat() if positions_available else None,
        "symbol": str(snapshot.get("symbol", ""))[:32],
        "timeframe": str(snapshot.get("timeframe", ""))[:12],
        "server_time": str(snapshot.get("server_time", ""))[:40],
        "account_currency": str(snapshot.get("account_currency", ""))[:12],
        "bar_time": str(snapshot.get("bar_time", ""))[:40],
        "bid": snapshot.get("bid") if _finite_number(snapshot.get("bid")) else None,
        "ask": snapshot.get("ask") if _finite_number(snapshot.get("ask")) else None,
        "spread_points": snapshot.get("spread_points") if _finite_number(snapshot.get("spread_points")) else None,
        "balance": snapshot.get("balance") if _finite_number(snapshot.get("balance")) else None,
        "equity": snapshot.get("equity") if _finite_number(snapshot.get("equity")) else None,
        "position": str(snapshot.get("position", ""))[:12],
        "position_pnl": snapshot.get("position_pnl") if _finite_number(snapshot.get("position_pnl")) else None,
        "ai_enabled": _bool_or_none(snapshot.get("ai_enabled")),
        "ai_shadow": _bool_or_none(snapshot.get("ai_shadow")),
        "legacy_signal_fallback": _bool_or_none(snapshot.get("legacy_signal_fallback")),
        "terminal_connected": _bool_or_none(snapshot.get("terminal_connected")),
        "terminal_trade_allowed": _bool_or_none(snapshot.get("terminal_trade_allowed")),
        "ea_trade_allowed": _bool_or_none(snapshot.get("ea_trade_allowed")),
        "candles": candles,
        "chart_source": chart_source,
        "positions_available": positions_available,
        "open_positions": positions,
    }
    # Preserve an immediate transaction update if an older EA omits the new field.
    if not positions_available and latest_market_state and latest_market_state.get("symbol") == state["symbol"]:
        state["positions_available"] = latest_market_state.get("positions_available", False)
        state["positions_received_at"] = latest_market_state.get("positions_received_at")
        state["open_positions"] = latest_market_state.get("open_positions")
    latest_market_state = state


async def _ingest_snapshot(snapshot: dict[str, Any]) -> None:
    """Record dashboard state, score pending shadow setups and log equity for this bar."""
    _record_market_snapshot(snapshot)
    if brain is None or latest_market_state is None:
        return
    try:
        if _finite_number(snapshot.get("atr_m5")):
            context = await brain.analyzer.analyze(snapshot)
            brain.latest_context = {"bar_time": latest_market_state["bar_time"], **context}
        constraints = snapshot.get("constraints") if isinstance(snapshot.get("constraints"), dict) else {}
        max_hold = constraints.get("max_hold_bars")
        await brain.shadow.resolve(latest_market_state["candles"], int(max_hold) if _finite_number(max_hold) else None)
        t = bar_epoch(latest_market_state["bar_time"])
        if t is not None and (latest_market_state["equity"] is not None or latest_market_state["balance"] is not None):
            await brain.memory.log_equity(t, latest_market_state["balance"], latest_market_state["equity"])
    except Exception as exc:
        log.warning("Snapshot bookkeeping failed: %s", exc)


def _fail_closed(snapshot: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "action": "NO_TRADE",
        "confidence": 0.0,
        "regime": "unclear",
        "setup": "none",
        "stop_atr": settings.MIN_STOP_ATR,
        "target_r": settings.MIN_TARGET_R,
        "reason": reason,
        "bar_time": str(snapshot.get("bar_time", "")),
    }


@app.on_event("startup")
async def startup_event() -> None:
    global brain
    if len(settings.BRIDGE_TOKEN) < 32 or settings.BRIDGE_TOKEN == "replace_with_a_unique_random_secret_at_least_32_characters":
        raise RuntimeError("BRIDGE_TOKEN must be a unique secret with at least 32 characters")
    await init_db()
    brain = AIBrain()
    log.info("Cloud AI Trader Brain initialized and ready on %s:%s", settings.HOST, settings.PORT)


def verify_token(x_bridge_token: str = Header(..., alias="X-Bridge-Token")) -> str:
    """Validate incoming security token."""
    if not hmac.compare_digest(x_bridge_token, settings.BRIDGE_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid security token",
        )
    return x_bridge_token


# -----------------------------------------------------------------------------
# MT5 Integration Endpoints
# -----------------------------------------------------------------------------
@app.post("/v1/decision")
async def get_decision(
    snapshot: dict[str, Any],
    token: str = Depends(verify_token),
) -> dict[str, Any]:
    """Endpoint called by MT5 EA on every new candle."""
    if brain is None:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    try:
        if str(snapshot.get("symbol", "")).upper().startswith("XAUUSD"):
            await _ingest_snapshot(snapshot)
        # Chart and exact position details are for the dashboard only; the analysis
        # pipeline retains its existing compact decision payload.
        dashboard_only = {
            "chart_candles_m5", "open_positions", "account_currency", "ai_enabled", "ai_shadow",
            "legacy_signal_fallback", "terminal_connected", "terminal_trade_allowed", "ea_trade_allowed",
        }
        decision_snapshot = {key: value for key, value in snapshot.items() if key not in dashboard_only}
        # Answer before the EA's WebRequest timeout; a late answer is useless to it.
        return await asyncio.wait_for(brain.process_bar(decision_snapshot), timeout=settings.DECISION_BUDGET_S + 2.0)
    except asyncio.TimeoutError:
        log.warning("Decision exceeded %.0fs budget; fail-closed", settings.DECISION_BUDGET_S + 2.0)
        return _fail_closed(snapshot, "Fail-closed: decision exceeded time budget")
    except Exception as exc:
        log.exception("Error processing bar decision: %s", exc)
        return _fail_closed(snapshot, f"Fail-closed: Error in bridge ({type(exc).__name__})")


@app.post("/v1/market")
async def update_market(
    snapshot: dict[str, Any],
    token: str = Depends(verify_token),
) -> dict[str, Any]:
    """Receive an MT5 chart snapshot without invoking the AI or changing trading."""
    if not str(snapshot.get("symbol", "")).upper().startswith("XAUUSD"):
        raise HTTPException(status_code=400, detail="unsupported symbol")
    await _ingest_snapshot(snapshot)
    return {"status": "ok", "received_at": latest_market_state["market_received_at"] if latest_market_state else None}


@app.post("/v1/trade_opened")
async def trade_opened(
    trade: dict[str, Any],
    token: str = Depends(verify_token),
) -> dict[str, Any]:
    """Broker-confirmed entry from the EA; tagged with the AI decision that preceded it."""
    if brain is None:
        raise HTTPException(status_code=503, detail="Brain not initialized")
    numeric = ("ticket", "entry_price", "volume")
    if str(trade.get("direction", "")).upper() not in {"BUY", "SELL"} or any(not _finite_number(trade.get(k)) for k in numeric):
        raise HTTPException(status_code=400, detail="trade is missing valid broker values")
    approved = brain.last_approved or {}
    record = {
        "ticket": int(trade["ticket"]),
        "symbol": trade.get("symbol", "XAUUSD"),
        "direction": str(trade["direction"]).upper(),
        "entry_price": float(trade["entry_price"]),
        "sl_price": float(trade.get("sl_price") or 0.0),
        "tp_price": float(trade.get("tp_price") or 0.0),
        "lot_size": float(trade["volume"]),
        "open_time": trade.get("open_time"),
        "risk_usd": float(trade["risk_usd"]) if _finite_number(trade.get("risk_usd")) and trade["risk_usd"] > 0 else None,
        "regime": approved.get("regime", "unclear"),
        "setup": approved.get("setup", "none"),
        "ai_confidence": approved.get("confidence", 0.0),
        "ai_reason": approved.get("reason", ""),
    }
    await brain.memory.log_trade_opened(record)
    return {"status": "ok", "ticket": record["ticket"]}


def _hold_bars(open_time: Any, close_time: Any) -> int:
    start, end = bar_epoch(str(open_time or "")), bar_epoch(str(close_time or ""))
    return max(0, (end - start) // 300) if start is not None and end is not None else 0


@app.post("/v1/trade_closed")
async def trade_closed(
    trade_result: dict[str, Any],
    token: str = Depends(verify_token),
) -> dict[str, Any]:
    """Endpoint called by MT5 EA when an order closes to trigger AI reflection."""
    if brain is None:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    if not trade_result.get("hold_bars"):
        trade_result["hold_bars"] = _hold_bars(trade_result.get("open_time"), trade_result.get("close_time"))
    # The ledger update is quick; the LLM reflection runs after the EA has its answer.
    trade = await brain.memory.log_trade_closed(trade_result)
    asyncio.create_task(_reflect(trade_result, trade))
    return {"status": "ok", "ticket": trade.get("ticket"), "pnl_r": trade.get("pnl_r")}


async def _reflect(trade_result: dict[str, Any], trade: dict[str, Any]) -> None:
    try:
        await brain.process_trade_closed(trade_result, trade)
    except Exception as exc:
        log.exception("Error processing trade reflection: %s", exc)


@app.post("/v1/positions")
async def sync_positions(
    update: dict[str, Any],
    token: str = Depends(verify_token),
) -> dict[str, Any]:
    """Receive broker-confirmed EA positions after an MT5 trade transaction."""
    global latest_market_state
    symbol = str(update.get("symbol", ""))
    if not symbol.upper().startswith("XAUUSD"):
        raise HTTPException(status_code=400, detail="unsupported symbol")
    positions = _positions_from_payload(update.get("positions"), symbol)
    received_at = datetime.now(timezone.utc).isoformat()
    server_time = str(update.get("server_time", ""))[:40]

    if latest_market_state is None or latest_market_state.get("symbol") != symbol:
        latest_market_state = {
            "available": False,
            "market_received_at": None,
            "symbol": symbol[:32],
            "timeframe": "M5",
            "server_time": server_time,
            "account_currency": str(update.get("account_currency", ""))[:12],
            "bar_time": "",
            "bid": None,
            "ask": None,
            "spread_points": None,
            "balance": None,
            "equity": None,
            "position": "",
            "position_pnl": None,
            "candles": [],
            "chart_source": "none",
        }
    latest_market_state["positions_available"] = True
    latest_market_state["open_positions"] = positions
    latest_market_state["positions_received_at"] = received_at
    if server_time:
        latest_market_state["positions_server_time"] = server_time
    if update.get("account_currency"):
        latest_market_state["account_currency"] = str(update["account_currency"])[:12]
    return {"status": "ok", "positions": len(positions), "received_at": received_at}


# -----------------------------------------------------------------------------
# Monitoring & Dashboard Endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict[str, Any]:
    """System health status."""
    return {
        "status": "online",
        "model": settings.LLM_MODEL,
        "fallback_model": settings.LLM_FALLBACK_MODEL,
        "shadow_mode": settings.SHADOW_MODE,
        "enable_trading": settings.ENABLE_TRADING,
        "gemini_api_configured": bool(settings.GEMINI_API_KEY),
        # Minutes until each out-of-quota model may be used again (empty when all usable).
        "quota_wait_min": {
            m: round(quota_wait_s(m) / 60) for m in (settings.LLM_MODEL, settings.LLM_FALLBACK_MODEL) if quota_wait_s(m) > 0
        },
    }


@app.get("/api/trades")
async def api_trades() -> list[dict[str, Any]]:
    if brain is None:
        return []
    return await brain.memory.get_recent_trades(limit=25)


@app.get("/api/decisions")
async def api_decisions() -> list[dict[str, Any]]:
    if brain is None:
        return []
    return await brain.memory.get_recent_decisions(limit=30)


@app.get("/api/performance")
async def api_performance() -> dict[str, Any]:
    if brain is None:
        return {}
    return await brain.memory.get_performance_summary()


@app.get("/api/market")
async def api_market() -> dict[str, Any]:
    """Latest market and position facts received from the configured MT5 EA."""
    if latest_market_state is None:
        return {"available": False, "market_received_at": None, "positions_available": False, "open_positions": None, "candles": []}
    return dict(latest_market_state)


@app.get("/api/knowledge")
async def api_knowledge() -> dict[str, Any]:
    if brain is None:
        return {}
    return {
        "trading_rules": brain.memory.get_trading_rules(),
        "strategy_preferences": brain.memory.get_strategy_preferences(),
        "market_insights": brain.memory.get_market_insights(),
    }


def _backtest_summary() -> dict[str, Any] | None:
    path = settings.BASE_DIR / "data" / "backtest_summary.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError):
        return None


@app.get("/api/overview")
async def api_overview() -> dict[str, Any]:
    """Everything the dashboard needs in one request."""
    market = await api_market()
    if brain is None:
        return {"health": await health_check(), "market": market}
    return {
        "health": await health_check(),
        "market": market,
        "context": brain.latest_context,
        "performance": await brain.memory.get_performance_summary(),
        "shadow": await brain.shadow.summary(),
        "decisions": await brain.memory.get_recent_decisions(limit=40),
        "trades": await brain.memory.get_recent_trades(limit=25),
        "equity": await brain.memory.get_equity_curve(),
        "backtest": _backtest_summary(),
    }


@app.get("/")
async def root_view() -> RedirectResponse:
    """Redirect root path to /dashboard."""
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view() -> HTMLResponse:
    html_file = settings.BASE_DIR / "dashboard" / "templates" / "index.html"
    if not html_file.exists():
        return HTMLResponse("<h3>Dashboard template not found</h3>", status_code=404)
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))
