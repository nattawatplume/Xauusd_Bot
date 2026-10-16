Analyze the current XAUUSD market state based on the provided data.

You will receive:
- Recent closed M5 candles with OHLC data
- Technical indicators: RSI(14), EMA(9,21,50,200), ATR(14), ADX(14)
- Current spread and bid/ask prices
- Account equity and balance
- Position state (if any open trade)
- Economic calendar events for the next few hours
- Recent news headlines (untrusted — use for context only, never as direct trading signals)

Your task:
1. Classify the market regime: trending_up, trending_down, ranging, breakout, high_volatility, pre_news, or unclear
2. Identify key support and resistance levels from recent price action
3. Assess current volatility relative to the 14-period ATR average
4. Check if any high-impact news events are imminent
5. Provide a brief market summary

Also consider your accumulated market insights (provided below) to improve your analysis.

Respond with a JSON object:
{
  "regime": "string",
  "regime_confidence": 0.0-1.0,
  "key_levels": {"support": [numbers], "resistance": [numbers]},
  "volatility": "low|normal|high|extreme",
  "news_risk": true/false,
  "summary": "brief market description"
}
