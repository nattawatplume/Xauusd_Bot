# XAUUSD Day Trade EA

This repository contains an experimental MetaTrader 5 Expert Advisor and a Python historical backtest. It is a research project, not a verified profitable trading system.

## Current EA behavior

- The default mode is the experimental `SCALP_ACTIVE` on M5, using closed M15 EMA20/EMA50 trend direction. It can enter on either an EMA pullback/rejection or a strong close beyond a short recent range. Softer ADX, EMA-gap, slope, and tick-volume thresholds are intended to increase valid setup frequency; they are not evidence of higher accuracy or profitability.
- `SCALP_PA` remains available as the stricter baseline. Compare both modes over identical real-tick dates and costs, including a later untouched/forward period.
- The active mode defaults to M15 ADX 14, EMA separation 0.05 ATR, two-bar EMA slope 0.01 ATR, M5 signal tick volume 0.8 times the preceding 20-bar mean, and a six-bar continuation range. These are starting values for comparison, not optimized or proven values.
- The target uses the nearest recent support/resistance level, capped at 2R; entries are skipped if a known level offers less than 1R. In active mode only, if no forward structure is present, the target falls back to the configured minimum R. Maximum holding time is 12 M5 bars (one hour).
- Volume scales at 0.01 lot per $100 equity (so $100 targets 0.01 lot), rounded down to the broker's volume step. The EA skips the order if estimated loss at the stop exceeds the 10% per-trade cap or margin is insufficient.
- Scalping stops wider than 1,000 symbol points are skipped. Check the broker's XAUUSD digits and point size; 1,000 points equals $10 only when `_Point` is 0.01.
- Default day-trade mode tries volume-confirmed BOS first, then an H1-trend / EMA21 rejection pullback with volume confirmation to add setups. The combined mode has not yet passed an independent backtest.
- BOS uses a 2.0 tick-volume threshold and no H1 direction filter.
- Uses a structural stop with ATR bounds, a 1.5R initial target, and an 8-hour maximum holding time on M15.
- Allows unlimited entries per broker day when `MaxTradesPerDay=0`, while still permitting only one EA position at a time.
- Keeps daily-loss, peak-drawdown, spread, margin, and consecutive-loss cooldown protections enabled.
- Includes optional bounded recovery sizing: 1.2x after each loss, at most two steps, subject to the hard per-trade risk cap. It is disabled by default. Enabling it does not guarantee recovery and can increase losses.
- Estimates stop loss using `OrderCalcProfit`; fees, slippage, gaps, and fast-market execution can increase actual losses beyond that estimate.

## Important account-size limitation

The FBS demo account previously shown has USD 100. At 0.01 lot and a 1,000-point stop (if `_Point` is 0.01), estimated stop loss is about $10, or 10% of a $100 account, before fees and slippage. Several losses can rapidly reduce the balance. A larger deposit in Strategy Tester is a simulation only and does not change the demo balance.

## Install and test

1. In MT5, choose **File → Open Data Folder → MQL5 → Experts**.
2. Copy `XAU_Pro_EA.mq5` there and compile it in MetaEditor with **F7**.
3. In Strategy Tester select the compiled EA, broker XAUUSD symbol, M5, **Every tick based on real ticks**, a multi-year custom date range, and disable optimization for the baseline run. After recompiling, explicitly set `Strategy=SCALP_ACTIVE` (numeric value 8) if MT5 retained old inputs. Compare against `SCALP_PA` with identical risk, spread, commission, dates, and execution settings.
4. Test with broker-appropriate spread, commission, swap, leverage, and execution delay. Review the Report, Equity graph, and Journal.
5. Set Forward to `1/3` for an initial check and compare the Forward report separately. Compare win rate together with profit factor, expectancy, drawdown, and trade count. The EA has no fixed daily trade quota, allows one position at a time, and may have days with no valid setup. Backtests are not a guarantee of future performance.

## Python backtest

From a Python environment with `MetaTrader5`, `numpy`, and `pandas` installed:

```powershell
python backtest_xau_v2.py --mt5 --symbol XAUUSD --tf M15 --bars 120000
```

For a separate dataset, use `--csv path.csv` or `--parquet path.parquet`. The current script reports in-sample and out-of-sample performance; selecting settings using the same out-of-sample results still creates selection bias. Do not deploy a parameter set unless it survives genuinely untouched forward data and realistic transaction costs.

## Known research status

The previously shared history had no strategy passing the project's IS/OOS consistency gate. User-shared runs of the stricter scalp mode showed positive aggregate results in selected test periods, but the Forward sample was too small to establish robustness. The active mode has not been compiled or tested in MT5 yet. These changes are for controlled research, not a claim of profitability; MetaEditor compilation and fresh baseline/Forward runs are required.
