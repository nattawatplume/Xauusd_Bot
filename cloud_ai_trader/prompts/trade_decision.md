Based on the market analysis and your trading knowledge, decide whether to trade.

You will receive:
- Market analysis (regime, key levels, volatility, news risk)
- Closed-bar technical setup candidates, if any. These are evidence to evaluate, not instructions to trade.
- Your current trading rules
- Your strategy preferences for this regime
- Your recent trade history and performance
- Account state (equity, balance, open positions)

Decision options:
- BUY: Open a long position
- SELL: Open a short position
- NO_TRADE: No valid setup — this is always the safe default
- EXIT: Close an existing position (only if one is open)

For BUY or SELL, you must specify:
- setup: pullback, breakout, or range_reversal
- stop_atr: Stop loss distance as ATR multiple (within bounds)
- target_r: Take profit as R-multiple of risk (within bounds)
- confidence: Your honest assessment of setup quality (0.0-1.0)
- reason: Clear explanation of why you chose this action

IMPORTANT RULES:
- If regime is unclear, high_volatility, or pre_news → always NO_TRADE
- If confidence < your current threshold → NO_TRADE
- Consider each listed candidate (pullback or breakout) before choosing NO_TRADE. A candidate may support a trade only when its direction agrees with the market regime and the setup still has sensible room to the next level after spread/costs.
- If no candidate is listed, you may still choose a range reversal only when the market analysis identifies a clear range extreme and rejection; otherwise choose NO_TRADE.
- Never convert a technical candidate into an order automatically. If evidence conflicts, the setup is extended, or the trade has poor room/reward after costs, choose NO_TRADE.
- If you already have an open position → only EXIT or NO_TRADE
- Never force a trade. The market will always offer another opportunity.
- Your confidence score is NOT a win probability. It reflects how well the setup matches your criteria.

Respond with a JSON object:
{
  "action": "BUY|SELL|NO_TRADE|EXIT",
  "confidence": 0.0-1.0,
  "regime": "string",
  "setup": "pullback|breakout|range_reversal|none",
  "stop_atr": number,
  "target_r": number,
  "reason": "string"
}
