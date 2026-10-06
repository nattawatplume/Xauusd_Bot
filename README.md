# XAUUSD Day Trade EA

This repository contains an experimental MetaTrader 5 Expert Advisor and a Python historical backtest. It is a research project, not a verified profitable trading system.

## Current EA behavior

- The default mode is `SCALP_PA` on M5, using closed M15 trend direction, as the simpler comparison baseline. The more permissive `SCALP_ACTIVE` mode remains available for experiments; it is not the default because the latest user-shared run lost money.
- Compare `SCALP_PA` and `SCALP_ACTIVE` over identical real-tick dates and costs, including a later untouched/forward period.
- The active mode uses M15 ADX 14, EMA separation 0.05 ATR, two-bar EMA slope 0.01 ATR, M5 signal tick volume 0.8 times the preceding 20-bar mean, and a six-bar continuation range. These are experimental, not optimized or proven values.
- The target uses the nearest recent support/resistance level, capped at 2R; entries are skipped if a known level offers less than 1R. In active mode only, if no forward structure is present, the target falls back to the configured minimum R. Maximum holding time is 12 M5 bars (one hour).
- Volume scales at 0.01 lot per $100 equity (so $100 targets 0.01 lot), rounded down to the broker's volume step. The default estimated per-trade risk cap is 5%; if the broker's minimum lot exceeds it, the EA skips the order. The cap does not cover all slippage, gaps, or fees.
- Scalping stops wider than 1,000 symbol points are skipped. Check the broker's XAUUSD digits and point size; 1,000 points equals $10 only when `_Point` is 0.01.
- Default day-trade mode tries volume-confirmed BOS first, then an H1-trend / EMA21 rejection pullback with volume confirmation to add setups. The combined mode has not yet passed an independent backtest.
- BOS uses a 2.0 tick-volume threshold and no H1 direction filter.
- Uses a structural stop with ATR bounds, a 1.5R initial target, and an 8-hour maximum holding time on M15.
- Allows unlimited entries per broker day when `MaxTradesPerDay=0`, while still permitting only one EA position at a time.
- Keeps daily-loss, peak-drawdown, spread, margin, and consecutive-loss cooldown protections enabled.
- Bounded martingale recovery sizing remains available as an experiment but is disabled by default. It can double the base lot after losses for at most two steps, subject to the per-trade, daily-loss, drawdown, and margin guards. It cannot create a trading edge or guarantee recovery.
- Estimates stop loss using `OrderCalcProfit`; fees, slippage, gaps, and fast-market execution can increase actual losses beyond that estimate.

## Important account-size limitation

The FBS demo account previously shown has USD 100. At 0.01 lot and a 1,000-point stop (if `_Point` is 0.01), estimated stop loss is about $10, or 10% of a $100 account, before fees and slippage. That exceeds the new 5% default cap, so the EA will skip this order unless the actual stop or lot is smaller. Several losses can rapidly reduce the balance. A larger deposit in Strategy Tester is a simulation only and does not change the demo balance.

## Install and test

1. In MT5, choose **File → Open Data Folder → MQL5 → Experts**.
2. Copy `XAU_Pro_EA.mq5` there and compile it in MetaEditor with **F7**.
3. In Strategy Tester select the compiled EA, broker XAUUSD symbol, M5, **Every tick based on real ticks**, a multi-year custom date range, and disable optimization. After recompiling, reset retained Inputs or explicitly set `Strategy=SCALP_PA` (numeric value 7), `EnableRecoverySizing=false`, and `MaxRiskPercent=5`. Compare `SCALP_ACTIVE` separately, changing only the strategy input.
4. Test with broker-appropriate spread, commission, swap, leverage, and execution delay. Review the Report, Equity graph, and Journal.
5. Set Forward to `1/3` for an initial check and compare the Forward report separately. Compare win rate together with profit factor, expectancy, drawdown, and trade count. The EA has no fixed daily trade quota, allows one position at a time, and may have days with no valid setup. Backtests are not a guarantee of future performance.

## Python backtest

From a Python environment with `MetaTrader5`, `numpy`, and `pandas` installed:

```powershell
python backtest_xau_v2.py --mt5 --symbol XAUUSD --tf M15 --bars 120000
```

For a separate dataset, use `--csv path.csv` or `--parquet path.parquet`. The current script reports in-sample and out-of-sample performance; selecting settings using the same out-of-sample results still creates selection bias. Do not deploy a parameter set unless it survives genuinely untouched forward data and realistic transaction costs.

## Known research status

User-shared runs include an aggregate positive period for one configuration, but the latest active-mode report showed net loss USD 16.21 with PF 0.43 and its Forward result showed two losing trades totaling USD 20.90. This does not establish a robust edge. See [RESEARCH.md](RESEARCH.md) for the evidence review and validation plan. These changes are for controlled research, not a claim of profitability; MetaEditor compilation and fresh baseline/Forward runs are required.
