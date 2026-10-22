# Strategy Preferences (AI-Managed)

> Last updated: Tuned for realistic intraday gold execution (M5 timeframe)
> The AI dynamically selects setups based on market regime and price structure.

## Regime → Strategy Matrix

| Market Regime | Preferred Strategy | Confidence Required | Entry Criteria |
|---|---|---|---|
| Strong Trend (ADX > 25) | Trend Pullback or Confirmed Continuation | 0.50 | Consider a closed-bar rejection/engulfing at the M5 EMA9/21 zone, or a strong close beyond the recent six-bar range in the M15 trend direction. |
| Moderate Trend (ADX 16 - 25) | Confirmed Pullback or Breakout | 0.50 | Require M15 EMA20/50 alignment and a closed M5 rejection/engulfing near EMA9/21, or a strong close beyond the previous six-bar range. |
| Breakout (Price breaks Donchian 15-20) | Momentum Breakout | 0.50 | Close beyond recent swing high/low with expanding candle size. |
| Ranging / Flat (ADX < 18) | Range Reversal / Stand Aside | 0.65 | Reversal only at extreme Support/Resistance with pinbar/rejection. |
| High Volatility / News Spike | Stand Aside | N/A | Wait for spread to normalize (<35 pts) before entering. |

## Parameter Preferences
- Stop Loss: 1.2x - 1.5x ATR (Structural stop)
- Take Profit: 1.5R - 2.0R
- Confidence Threshold: 0.50 (balanced: sensitive to good setups, but filters random noise)
- Confidence is the model's self-rating, not a measured win probability; it cannot replace evidence or a cost-aware risk/reward check.
- Active Trading Hours: 07:00 - 22:00 server time
