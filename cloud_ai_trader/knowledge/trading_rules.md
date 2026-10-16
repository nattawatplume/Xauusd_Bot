# Trading Rules (AI-Managed)

> Last updated: Initial version
> These rules are maintained by the AI based on trading experience.
> The AI can add, modify, or remove rules through its reflection process.

## Entry Rules
1. Only trade when market regime is clearly identified (trending, ranging, or breakout)
2. Prefer NO_TRADE when evidence conflicts or confidence is below threshold
3. In trending markets: use pullback entries with trend direction confirmed by EMA50>EMA200 (up) or EMA50<EMA200 (down)
4. In ranging markets: avoid breakout entries; consider range_reversal only at clear support/resistance
5. In breakout conditions: enter only when ADX > 25 confirms momentum
6. Do not trade during high-impact USD news (NFP, FOMC, CPI) — pause 15 min before and 10 min after
7. Do not trade when spread exceeds 40 points (0.40 USD)

## Exit Rules
1. Use ATR-based stop loss (default 1.5x ATR)
2. Target minimum 1.5R reward-to-risk
3. Maximum holding time: 12 bars (1 hour on M5)
4. Move to break-even after 1.0R profit and minimum 2 bars held

## Risk Management
1. Never risk more than 5% per trade on a $100 account
2. Stop trading for the day if daily loss exceeds 8%
3. Maximum 5 trades per day — quality over quantity
4. After 3 consecutive losses, pause for 4 hours

## Market Conditions to Avoid
1. Low ADX (<15) with narrow Bollinger Bands — dead market
2. ATR spiking to 2x its 14-period average — abnormal volatility
3. Asian session (01:00-07:00 server time) unless session breakout setup
4. Friday afternoon (after 20:00 server time) — weekend gap risk
