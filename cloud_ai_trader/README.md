# XAU Cloud AI Trader

This directory contains an experimental FastAPI/Gemini decision service and a small SQLite-backed dashboard. It is a separate prototype from `AI_XAU_V1/service`, which uses the local Ollama bridge.

## Current scope

- MT5 can submit a market snapshot to `POST /v1/decision`; the service returns a structured proposal. The EA remains responsible for checking the response and sending or rejecting an order.
- The dashboard reads `GET /api/market`. The updated `AI_XAU_V1/MQL5/Experts/XAU_AI_Trader.mq5` sends up to 60 closed MT5 candles, the broker quote/account currency, and the EA's broker-confirmed positions. Entry/SL/TP changes are synced after MT5 trade transactions. The page draws only those supplied values; its quote refreshes on an EA snapshot, not on every tick.
- When AI trading filters block a new decision (or Shadow mode already has a position), the EA can send a market-only update to `POST /v1/market` without asking Gemini for another decision.
- Latest market data are held in service memory and are cleared when the service restarts. The next MT5 sync restores them. Older EA builds may provide only eight chart bars and may not expose exact position levels.
- MT5 can submit a close notification to `POST /v1/trade_closed`; the service records a reflection. The current EA notification does not include the opening event or initial cash risk, so this prototype cannot yet produce a complete trade ledger or trustworthy R-multiples from that notification alone.
- The dashboard and JSON endpoints display service memory. They are not an authenticated operator console; keep the service private.
- Daily review runs inside the Python process. It is not an independent scheduler and does not run while the service is stopped.
- AI review suggestions are recorded for a human to inspect. They do not automatically change live EA parameters or validated trading rules.
- This service does not independently place broker orders and its AI output is not evidence of a profitable strategy.

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

By default, the API binds to `127.0.0.1:8765`. Open `http://127.0.0.1:8765/dashboard` on that same machine. In MT5, allow the bridge URL under **Tools → Options → Expert Advisors** and set the EA URL/token inputs to match. Shadow mode and EA trading-disabled defaults should remain in place during observation.

For the dashboard's live-data panel, compile and attach the updated `AI_XAU_V1/MQL5/Experts/XAU_AI_Trader.mq5` in MetaEditor. `AI_XAU_V1/service` is a separate Ollama bridge and also defaults to port `8765`; do not start both services on that same port. The Cloud dashboard reads data from the FastAPI process in this directory.

## VPS

The Docker mapping also binds to loopback. This is suitable when MT5 and the service run on the same VPS. For remote MT5-to-VPS traffic, use HTTPS through a properly configured reverse proxy, expose only the API routes needed by MT5, and do not publish the dashboard or unauthenticated `/api/*` routes to the public internet. The setup shell script only installs host prerequisites; it does not configure TLS, firewall policy, service supervision, MT5, or broker login.

## Known limitations before any live use

- The EA's close webhook reports a deal ticket, not a complete position ledger; partial closes and entry metadata are not reconciled.
- Risk caps are enforced in the EA. Cloud settings such as `MAX_RISK_PCT`, daily loss, drawdown, and trades-per-day are configuration placeholders and are not a second independent risk engine.
- Market/news analysis depends on fields supplied by the EA and model output. This Cloud prototype does not fetch an independent news feed.
- The SQLite code uses native `sqlite3`; the `DB_URL` setting and SQLAlchemy model declarations are not the active persistence path.
- No compile, broker connection, historical evaluation, or demo forward run is implied by this source tree.
