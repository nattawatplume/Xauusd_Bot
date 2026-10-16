Reflect on a completed trade to extract lessons.

You will receive:
- The original decision: what you decided and why
- The trade result: entry price, exit price, P&L, how long it was held
- Market conditions at entry and at exit
- Your current trading rules

Analyze:
1. Was your market regime classification correct?
2. Was your entry timing good, early, or late?
3. Was your stop loss appropriate? Too tight (stopped out prematurely)? Too wide (unnecessary risk)?
4. Was your target appropriate? Too ambitious? Too conservative?
5. What would you do differently if you saw the same setup again?
6. Is there a lesson that should be added to your trading rules?

Be honest and specific. Vague reflections like "should have been more careful" are useless. Instead say: "ADX was 18, below the 20 threshold — I should not have classified this as a trending market."

Respond with a JSON object:
{
  "trade_assessment": "good_entry|bad_entry|good_exit|bad_exit|unlucky|lucky",
  "regime_was_correct": true/false,
  "entry_timing": "good|early|late",
  "sl_assessment": "appropriate|too_tight|too_wide",
  "tp_assessment": "appropriate|too_ambitious|too_conservative",
  "key_lesson": "string — the most important takeaway",
  "suggested_rule_change": "string or null — a specific rule to add/modify/remove",
  "suggested_param_change": {"param": "value"} or null
}
