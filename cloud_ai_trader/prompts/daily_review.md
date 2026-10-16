Conduct your end-of-day review of all trading activity.

You will receive:
- All trades taken today (with results)
- All decisions made today (including NO_TRADE decisions and their reasons)
- Your current trading rules and strategy preferences
- Account performance summary

Your review should:
1. Summarize the day: how many trades, wins, losses, net P&L in R
2. What was the dominant market regime today?
3. Did your regime classification accuracy improve, stay the same, or get worse?
4. Identify any patterns: Are losses clustered around certain times/regimes/setups?
5. Were there good setups you missed (NO_TRADE that would have been profitable)?
6. Were there trades you should have avoided?
7. Propose specific rule changes if patterns are clear (NOT after a single bad trade)
8. Propose parameter adjustments if data supports it (need at least 5 similar trades)

Do NOT change rules after a single trade outcome. Pattern recognition requires repeated observations.

Respond with a JSON object:
{
  "summary": "string",
  "dominant_regime": "string",
  "regime_accuracy": "improved|same|worse",
  "patterns_identified": ["string"],
  "missed_opportunities": ["string"],
  "trades_to_avoid": ["string"],
  "proposed_rule_changes": [{"type": "add|modify|remove", "rule": "string", "reason": "string"}],
  "proposed_param_changes": [{"param": "string", "current": number, "proposed": number, "reason": "string"}]
}
