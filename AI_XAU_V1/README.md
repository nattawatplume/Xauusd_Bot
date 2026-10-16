# XAU AI Trader v2.00 (local-model prototype)

This folder is a separate prototype. The existing root-level `XAU_Pro_EA.mq5` and backtest scripts are preserved. The new EA uses a local Ollama model to classify the market regime and propose a setup/action; the EA validates the response and remains the only component allowed to submit orders.

## What the AI receives and decides

- Eight closed M5 candles, M5 RSI/EMA/ATR, M15 EMA/ADX/ATR, bid/ask/spread, account equity/balance, EA position state, and upcoming high-impact USD events from the MT5 economic calendar.
- Recent headline metadata from the public GDELT DOC search endpoint. This is a convenience feed without a trading-service uptime guarantee; the headline list can be empty or stale.
- A structured decision: `BUY`, `SELL`, `NO_TRADE`, or `EXIT`; setup (`pullback`, `breakout`, `range_reversal`); market regime; confidence; stop distance in ATR; target in R; and a short reason.
- `EXIT` is only accepted for this EA's position. The EA rejects stale bar responses, low confidence, invalid actions, and stop/target values outside configured bounds.

The selected local model is `qwen3:4b` through Ollama. It is an open-weight general model, not a model trained or validated to predict XAUUSD returns. The model download is about 2.5 GB. Running it has no per-request AI API fee, but still consumes computer/VPS resources and electricity. This prototype does not claim profitability or a proven trading edge.

## Safety defaults

- `AIShadowMode=true`, `AIEnableTrading=false`: requests and logs AI decisions but sends no new AI trades.
- `AIEnableTrading=true` is rejected while `AIShadowMode=true`; both must be changed deliberately before the EA will send orders.
- Per-trade risk cap defaults to 1%; daily equity stop is 1%; peak-equity stop is 5%; no more than 3 entries per broker day; at most one position at a time. These are caps, not a minimum trade quota. The AI may return `NO_TRADE` every day.
- Martingale/recovery sizing is disabled for AI trades even if its legacy input is changed.
- The MT5 EA applies spread, margin, lot, stop-distance, news-window, daily-loss, loss-streak, time-exit, and equity kill-switch checks. If the AI bridge times out or returns invalid data, it fails closed and does not open a trade.
- The EA uses a distinct default magic number (`234568`) so it will not manage trades from the legacy EA (`234567`). Do not attach multiple copies of this new EA using the same magic number to the same symbol/account.
- A distinct magic number prevents cross-management, but both EAs could still open separate positions on XAUUSD. For the AI demo observation, remove/disable the legacy EA on that account or use a separate demo account. Do not run both on the same symbol/account during this phase.
- Several legacy strategy inputs remain visible because the risk and trade-management code was reused. They are ignored while `EnableLegacySignalFallback=false` and the AI branch is active. Keep that fallback disabled.

AI confidence is only the model's self-assessed score; it is **not** a measured probability that a trade will win. A 3-trades-per-day cap does not mean there will be 3 trades every day.

## Windows setup (demo/shadow first)

1. Install Ollama for Windows and Python 3.11 or newer.
2. Open PowerShell in this folder and run:

   ```powershell
   .\service\setup_windows.ps1
   ollama pull qwen3:4b
   ```

3. Edit `service\.env`. Set `AI_BRIDGE_TOKEN` to a long random secret. Never commit the `.env` file.
4. Start the local AI bridge:

   ```powershell
   .\service\start_ai_bridge.ps1
   ```

   The service binds only to `127.0.0.1`; do not expose it to the internet. Check `http://127.0.0.1:8765/health` in a browser. It should report `status: ok` and the configured model.

5. In MT5, open **File → Open Data Folder → MQL5 → Experts**, copy `MQL5\Experts\XAU_AI_Trader.mq5` there, then open it in MetaEditor and press **F7**. Confirm MetaEditor reports `0 errors`.
6. In MT5, open **Tools → Options → Expert Advisors**, enable **Allow WebRequest for listed URL**, and add `http://127.0.0.1:8765`. Attach `XAU_AI_Trader` to one **XAUUSD M5** demo chart. In EA Inputs, set `AIBridgeToken` to the same token from `.env`. Keep `AIShadowMode=true` and `AIEnableTrading=false` for the first observation period. Enable `Algo Trading`.
7. Review the MT5 **Experts/Journal** tab and `service\runtime\decisions.jsonl`. Confirm the bridge is reachable, bar timestamps match, news status is present, and decisions make sense. A response timeout/invalid response should result in no order.
8. Only after reviewing a substantial shadow sample and independently validating the trading rules should you consider setting `AIShadowMode=false` and `AIEnableTrading=true` on a demo account. Do not use a real account based only on a short sample.

## Running after closing your PC

Both MT5 and the Python bridge/Ollama process must run on the same always-on Windows machine because the EA calls `127.0.0.1`. For a future VPS deployment, copy this project to a Windows VPS, install MT5/Python/Ollama/model there, run `service\install_startup_task.ps1` from that Windows user session, and leave MT5 logged into the demo account. The task starts the bridge after that user logs in and restarts it after a process failure; MT5 must also be configured to start and logged into the demo account. A small 2 GB MT5-only VPS is not a suitable assumption for a local 4B model; measure RAM and inference time on the actual VPS before choosing it. The process may stay online continuously, while trading still stops during market closure, configured sessions, high-impact USD news, or risk limits.

## Important limitations

- MetaTrader's `WebRequest()` is synchronous and unavailable in Strategy Tester. Therefore this AI bridge cannot be validated as a historical MT5 tester run. First use shadow mode on a demo feed and review decisions; that is not a substitute for a sufficiently long forward evaluation.
- `AIShadowMode` records decisions but does not simulate fills, spread/slippage outcomes, or hypothetical profit. No new historical AI-replay harness is included yet.
- The free headline feed is not guaranteed timely or complete, and it does not replace a licensed news terminal. MT5 economic-calendar data are in broker server time; the EA uses that clock for event windows.
- This prototype has not been compiled by MetaEditor or observed on an MT5 demo account yet. Compile and perform the setup above before attaching it. It is not a signal to trade.

## Runtime files and secrets

Logs are written under `service\runtime\`. `.env`, decision logs, and model runtime data are excluded from Git. Do not put broker passwords or API secrets in the prompt, source code, or repository. This bridge listens on loopback and accepts only a matching `X-Bridge-Token`.
