# XAUUSD intraday strategy research notes

## Research question

Can a short-term technical rule be called the best or reliably profitable strategy for this broker's XAUUSD feed? The available evidence does not support that claim. Published results vary by market, sample, rule selection, and transaction-cost assumptions. Spot XAUUSD CFDs also differ from exchange-traded gold futures.

## Evidence reviewed

1. **Intraday precious-metal technical rules (2018).** The study uses 5-minute spot gold and silver observations from 2008–2014 and tests moving-average rules. Standard parameter choices showed no predictive power; some gold parameter combinations appeared significant after a broad parameter search. That makes independent validation essential, because picking the best combination from many trials risks selection bias. [Journal article](https://doi.org/10.1016/j.intfin.2017.06.005)
2. **Intraday technical trading in China's gold futures market (2022).** Using 5-minute Shanghai gold-futures data from 2018–2021, the author accounts for data snooping, costs, market conditions, and rebalance frequency. The reported technical rules did not produce persistently attractive out-of-sample performance. This is not the same instrument or broker feed, but it is a warning against assuming an in-sample gold rule will generalize. [Journal article](https://doi.org/10.1016/j.intfin.2021.101481)
3. **Time-series momentum and volatility scaling (2016).** A re-examination across 55 futures markets finds that reported momentum performance depends materially on volatility scaling and sample period. It does not establish a profitable M5 XAUUSD entry rule. [Journal article](https://doi.org/10.1016/j.finmar.2016.05.003)
4. **Deflated Sharpe Ratio (2014).** Bailey and López de Prado explain how repeated strategy/parameter selection inflates apparent backtest performance and propose correcting for multiple trials and non-normal returns. The practical implication here is to keep the number of variants small and record every tried variant rather than repeatedly tuning to the same Forward interval. [Paper](https://doi.org/10.3905/jpm.2014.40.5.094)
5. **Gold intraday market microstructure (2018).** Research on Tokyo and New York gold-futures activity finds different information/trading patterns across sessions. That supports measuring the user's broker feed by session, but does not by itself prove that a fixed London/New York time filter is profitable on this CFD feed. [RIETI discussion paper](https://www.rieti.go.jp/jp/publications/dp/17e120.pdf)

## Design decisions for this EA

- Keep one simple M5 setup with a closed-bar M15 direction filter as the baseline; retain the more permissive active mode as a separate candidate. Avoid adding several unrelated indicators or optimizing a large parameter grid.
- Disable Martingale by default. Position multiplication changes the distribution of wins and losses, but it does not improve the entry signal's expectancy. The previously shared active-mode report was negative (net -USD 16.21, PF 0.43), and its Forward report had two losses totaling -USD 20.90. Martingale would magnify exposure while the edge remains unproven.
- Use a 5% estimated per-trade risk cap by default. With a $100 balance and a broker minimum lot of 0.01, the EA may skip trades whose stop distance exceeds the cap. A skipped trade is safer than silently exceeding the stated risk limit. Verify the actual XAUUSD contract and volume step in MT5.
- Do not target a fixed number of trades per day. Keep the daily trade-count cap at zero (unlimited), but allow a day with no valid signal. Increasing frequency by relaxing filters is only acceptable if out-of-sample expectancy and drawdown remain acceptable after realistic costs.

## Validation plan

1. Compile in MetaEditor and confirm no errors.
2. Use MT5 Strategy Tester with the broker's XAUUSD symbol, M5, real ticks, realistic spread/commission/swap and execution delay, fixed $100 deposit, and optimization disabled.
3. Compare only a small predeclared set: baseline `SCALP_PA` with recovery off, then `SCALP_ACTIVE` with all other settings unchanged. Save the exact input set and report for each run.
4. Use a multi-year development period plus a genuinely untouched later period. A Forward report with only two trades is too small to judge performance; extend/roll the validation interval or gather more demo observations rather than tuning against those two trades.
5. Evaluate net expectancy, profit factor, maximum equity drawdown, loss streak, trade count, and per-session results together. Do not select a variant on win rate alone. If the unchanged rule fails Forward, reject it instead of repeatedly optimizing the same interval.

This process can reject weak candidates; it cannot guarantee future profit or make an intraday strategy risk-free.

## Cloud AI candidate backtest (2026-10-27)

`backtest_ai_candidates.py` replays the Cloud AI service's own `_technical_candidates` function (M15-trend pullback and six-bar breakout on M5) on FBS XAUUSD M5 bars from 2025-05-27 to 2026-10-27, with entry at the next bar open, the bar's recorded spread, 0.05 USD slippage per side, a same-bar stop/target touch counted as a loss, and a 12-bar time exit. The last third is the out-of-sample split.

| Plan | Trades | Win rate | Expectancy | PF |
|---|---|---|---|---|
| SL 1.5 ATR, TP 1.5R, costs | 5,429 | 41.5% | -0.054R | 0.90 |
| same, out-of-sample only | 1,836 | 40.8% | -0.062R | 0.88 |
| same, no costs | 5,409 | 44.1% | +0.011R | 1.02 |
| SL 1.0 ATR, TP 2.0R, costs | 6,337 | 33.6% | -0.087R | 0.87 |
| reversed signals, SL 1.5 ATR, TP 1.5R | 5,681 | 41.8% | -0.066R | 0.88 |

Every stop/target pair, setup type and session window tested was negative after costs. Before costs the candidates are close to breakeven, and reversing them also loses, which is what a signal with no directional information looks like. The LLM layer therefore has to supply the whole edge by vetoing; the service's shadow tracker measures whether its approved setups outperform the ones it rejects. Do not enable trading on the basis of the AI's confidence values or a short sample.
