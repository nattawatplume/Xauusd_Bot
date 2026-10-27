# XAU Cloud AI Trader

This directory contains an experimental FastAPI/Gemini decision service and a small SQLite-backed dashboard. It is a separate prototype from `AI_XAU_V1/service`, which uses the local Ollama bridge.

## How a decision is made

1. On every closed M5 bar the EA posts a snapshot to `POST /v1/decision` (or `POST /v1/market` when filters or an open position block a new entry).
2. Code, not the LLM, computes the market context: an ADX/RSI regime heuristic, a 30-minute high-impact USD news window from the EA's calendar data, and the rule-based setup candidates in `MarketAnalyzer._technical_candidates` (M15-trend pullback and six-bar breakout).
3. With no candidate and no open position the service answers `NO_TRADE` immediately; Gemini is not called. This removes most API calls and their latency.
4. With a candidate, Gemini receives the compact snapshot and the candidates and may only approve one (same direction) or veto it. Calls use `thinkingLevel=low`, fall back to `LLM_FALLBACK_MODEL`, and must finish within `DECISION_BUDGET_S` (default 15 s, below the EA's 20 s timeout). A late or failed call is fail-closed `NO_TRADE` with `ai_verdict=unavailable`.
5. The EA still applies every risk check and is the only component that can send an order.

## Shadow tracking: does the AI add value?

Every candidate bar is stored with an entry reference, ATR stop and R target, whether the AI approved it, rejected it, was unavailable, or a guardrail blocked it. Each later snapshot scores pending setups against the following M5 candles (stop/target touch, same-bar touch counts as a loss, exit after `max_hold_bars`). The dashboard compares the expectancy of "AI approved" against "AI rejected". The filter is only useful if approved setups clearly beat rejected ones over a meaningful sample (30+ each as a minimum, preferably hundreds).

## Trade ledger

The EA reports `POST /v1/trade_opened` (MT5 position id, entry, SL/TP, cash risk at the initial stop) and `POST /v1/trade_closed` (net profit including swap and commission across all deals of the position). The service computes the R multiple from the opening risk, records it, then runs the LLM reflection in the background so the EA is not blocked. Failed reflections are not written into the knowledge files.

## Research result (read before enabling trading)

`python backtest_ai_candidates.py --mt5 --bars 100000 --json cloud_ai_trader/data/backtest_summary.json` replays the exact candidate function on the broker's M5 history. On FBS XAUUSD from 2025-05 to 2026-10 (100,000 bars, average spread 0.24 USD, 0.05 USD slippage per side) the candidates, taken without the AI, returned about -0.05R per trade (PF 0.90, 5,429 trades) in both the in-sample and out-of-sample thirds. Before costs they were about breakeven (PF 1.02), and the reversed signals also lost, so the rules have no measurable edge and costs make them negative. No trading session or stop/target pair tested was positive. The LLM can only make this profitable by vetoing the losing majority very accurately; the shadow comparison above is how to find out. Keep `AIShadowMode=true`.

## Other notes

- Latest market data are held in service memory and are cleared when the service restarts. The next MT5 sync restores them.
- The dashboard and JSON endpoints are not an authenticated operator console; keep the service private.
- Daily review runs inside the Python process and does not run while the service is stopped. AI review suggestions are recorded for a human to inspect; they do not change live EA parameters.

## Local setup

Use Python 3.11 or newer. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY` and a unique random `BRIDGE_TOKEN` of at least 32 characters. Never commit `.env`. Google model availability, quotas, and pricing change; check Google's current [model lifecycle](https://ai.google.dev/gemini-api/docs/deprecations) before selecting a model. The default is `gemini-3.6-flash`.

Start with:

```powershell
python main.py
```

If another program already uses port 8766, set a different `PORT` in `.env` and change the EA input `AIBridgeURL` and the MT5 WebRequest allow-list to the same port.

By default, the API binds to `127.0.0.1:8766`, which matches the EA's default `AIBridgeURL`. Open `http://127.0.0.1:8766/dashboard` on that same machine. In MT5, allow the bridge URL under **Tools → Options → Expert Advisors** and set the EA URL/token inputs to match. Shadow mode and EA trading-disabled defaults should remain in place during observation.

For the dashboard's live-data panel, compile and attach the updated `AI_XAU_V1/MQL5/Experts/XAU_AI_Trader.mq5` in MetaEditor. `AI_XAU_V1/service` is a separate Ollama bridge on port `8765`; to use it instead, set the EA input `AIBridgeURL` to `http://127.0.0.1:8765/v1/decision`. The Cloud dashboard reads data from the FastAPI process in this directory.

## VPS

The Docker mapping also binds to loopback. This is suitable when MT5 and the service run on the same VPS. For remote MT5-to-VPS traffic, use HTTPS through a properly configured reverse proxy, expose only the API routes needed by MT5, and do not publish the dashboard or unauthenticated `/api/*` routes to the public internet. The setup shell script only installs host prerequisites; it does not configure TLS, firewall policy, service supervision, MT5, or broker login.

## Known limitations before any live use

- The EA's close webhook reports a deal ticket, not a complete position ledger; partial closes and entry metadata are not reconciled.
- Risk caps are enforced in the EA. Cloud settings such as `MAX_RISK_PCT`, daily loss, drawdown, and trades-per-day are configuration placeholders and are not a second independent risk engine.
- Market/news analysis depends on fields supplied by the EA and model output. This Cloud prototype does not fetch an independent news feed.
- The SQLite code uses native `sqlite3`; the `DB_URL` setting and SQLAlchemy model declarations are not the active persistence path.
- No compile, broker connection, historical evaluation, or demo forward run is implied by this source tree.
