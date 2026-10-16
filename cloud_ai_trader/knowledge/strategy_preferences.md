# Strategy Preferences (AI-Managed)

> Last updated: Initial version
> The AI adjusts these preferences based on which strategies work in which conditions.

## Regime → Strategy Matrix

| Market Regime | Preferred Strategy | Confidence Required | Notes |
|---|---|---|---|
| Strong Trend (ADX>25, EMA aligned) | Pullback | 0.65 | Wait for RSI to dip below 40 (buy) or above 60 (sell) |
| Weak Trend (ADX 20-25) | Pullback or Breakout | 0.70 | Need extra confirmation |
| Ranging (ADX<20) | NO_TRADE preferred | 0.80 | Only range_reversal at extreme levels |
| Breakout (price beyond Donchian 20) | Breakout | 0.70 | ADX must confirm momentum |
| High Volatility (ATR>2x avg) | NO_TRADE | N/A | Too risky for $100 account |
| Pre-News (within 15 min) | NO_TRADE | N/A | Always avoid |

## Current Parameter Preferences
- SL: 1.5x ATR (range: 0.5 - 3.0)
- Target: 1.5R (range: 1.0 - 4.0)
- Confidence threshold: 0.65 (range: 0.5 - 0.95)
- Preferred trading hours: 08:00 - 20:00 server time

## Strategy Performance Tracking
- Pullback: No data yet (new system)
- Breakout: No data yet
- Range Reversal: No data yet
