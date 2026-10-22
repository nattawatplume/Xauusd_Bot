"""FastAPI Bridge Server connecting MetaTrader 5 and the Cloud AI Brain."""
from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import settings
from brain.orchestrator import AIBrain
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
        decision = await brain.process_bar(snapshot)
        return decision
    except Exception as exc:
        log.exception("Error processing bar decision: %s", exc)
        return {
            "action": "NO_TRADE",
            "confidence": 0.0,
            "regime": "unclear",
            "setup": "none",
            "stop_atr": settings.MIN_STOP_ATR,
            "target_r": settings.MIN_TARGET_R,
            "reason": f"Fail-closed: Error in bridge ({type(exc).__name__})",
        }


@app.post("/v1/trade_closed")
async def trade_closed(
    trade_result: dict[str, Any],
    token: str = Depends(verify_token),
) -> dict[str, Any]:
    """Endpoint called by MT5 EA when an order closes to trigger AI reflection."""
    if brain is None:
        raise HTTPException(status_code=503, detail="Brain not initialized")

    try:
        reflection = await brain.process_trade_closed(trade_result)
        return {"status": "ok", "reflection": reflection}
    except Exception as exc:
        log.exception("Error processing trade reflection: %s", exc)
        return {"status": "error", "detail": str(exc)}


# -----------------------------------------------------------------------------
# Monitoring & Dashboard Endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
async def health_check() -> dict[str, Any]:
    """System health status."""
    return {
        "status": "online",
        "model": settings.LLM_MODEL,
        "shadow_mode": settings.SHADOW_MODE,
        "enable_trading": settings.ENABLE_TRADING,
        "gemini_api_configured": bool(settings.GEMINI_API_KEY),
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


@app.get("/api/knowledge")
async def api_knowledge() -> dict[str, Any]:
    if brain is None:
        return {}
    return {
        "trading_rules": brain.memory.get_trading_rules(),
        "strategy_preferences": brain.memory.get_strategy_preferences(),
        "market_insights": brain.memory.get_market_insights(),
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
