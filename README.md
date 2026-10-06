# XAUUSD Day Trade EA

This repository contains an experimental MetaTrader 5 Expert Advisor and a Python historical backtest. It is a research project, not a verified profitable trading system.

## Current EA behavior

- The default mode is `SCALP_PA` on M5, using an M15 trend filter. Other experimental strategies remain selectable.
- Scalping entries require a pullback/rejection or engulfing candle aligned with the M15 EMA trend, plus tick-volume confirmation. The quality-filter candidate also requires M15 ADX, EMA separation, and EMA slope thresholds; compare it with those filters set to zero on identical in-sample and untouched out-of-sample periods. It may skip many bars and cannot guarantee a fixed trade cadence or higher win rate.
- The target is the nearest recent support/resistance level, capped at 2R; entries are skipped if that level offers less than 1R. Maximum holding time is 12 M5 bars (one hour).
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
3. In Strategy Tester select the compiled EA, broker XAUUSD symbol, M5, **Every tick based on real ticks**, a multi-year custom date range, and disable optimization for the baseline run. After recompiling, reset Inputs to the EA defaults so the new scalp mode is selected.
4. Test with broker-appropriate spread, commission, swap, leverage, and execution delay. Review the Report, Equity graph, and Journal.
5. To evaluate the new signal-quality filters, run a baseline with `ScalpMinADX=0`, `ScalpMinTrendGapATR=0`, `ScalpMinSlopeATR=0`, and `ScalpVolMult=0.8`, then the candidate defaults, using identical dates and execution settings. Keep a later date range untouched for out-of-sample checking. Compare win rate together with profit factor, expectancy, drawdown, and trade count. Backtests are not a guarantee of future performance.

## Python backtest

From a Python environment with `MetaTrader5`, `numpy`, and `pandas` installed:

```powershell
python backtest_xau_v2.py --mt5 --symbol XAUUSD --tf M15 --bars 120000
```

For a separate dataset, use `--csv path.csv` or `--parquet path.parquet`. The current script reports in-sample and out-of-sample performance; selecting settings using the same out-of-sample results still creates selection bias. Do not deploy a parameter set unless it survives genuinely untouched forward data and realistic transaction costs.

## Known research status

The previously shared history had no strategy passing the project's IS/OOS consistency gate. A subsequent MT5 real-tick run of the EA reported PF 0.93, net loss USD 255 on USD 3,000, and 16.28% relative equity drawdown. The current EA changes are therefore for controlled research and safety, not a claim of profitability. MetaEditor compilation and a fresh tester run are still required after changes.
