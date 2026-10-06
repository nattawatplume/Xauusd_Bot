# XAUUSD Day Trade EA

This repository contains an experimental MetaTrader 5 Expert Advisor and a Python historical backtest. It is a research project, not a verified profitable trading system.

## Current EA behavior

- Default symbol is the chart symbol; attach the EA to the broker's XAUUSD symbol on M15.
- Default day-trade mode tries volume-confirmed BOS first, then an H1-trend / EMA21 rejection pullback with volume confirmation to add setups. The combined mode has not yet passed an independent backtest.
- BOS uses a 2.0 tick-volume threshold and no H1 direction filter.
- Uses a structural stop with ATR bounds, a 1.5R initial target, and an 8-hour maximum holding time on M15.
- Allows unlimited entries per broker day when `MaxTradesPerDay=0`, while still permitting only one EA position at a time.
- Keeps daily-loss, peak-drawdown, spread, margin, and consecutive-loss cooldown protections enabled.
- Includes optional bounded recovery sizing: 1.2x after each loss, at most two steps, subject to a hard 0.50% per-trade risk cap. It is disabled by default because the base strategy has not passed out-of-sample validation. Enabling it does not guarantee recovery and can increase losses.
- Calculates volume using `OrderCalcProfit` at the proposed stop, then skips the trade when the broker's minimum lot would exceed the risk cap.

## Important account-size limitation

The FBS demo account previously shown has USD 100. Gold's minimum volume may risk more than the EA's 0.50% cap at that balance. In that case the EA will correctly skip entries. Do not raise the risk cap just to force trades. A larger deposit in Strategy Tester is a simulation only and does not change the demo balance.

## Install and test

1. In MT5, choose **File → Open Data Folder → MQL5 → Experts**.
2. Copy `XAU_Pro_EA.mq5` there and compile it in MetaEditor with **F7**.
3. In Strategy Tester select the compiled EA, broker XAUUSD symbol, M15, **Every tick based on real ticks**, a multi-year custom date range, and disable optimization for the baseline run.
4. Test with broker-appropriate spread, commission, swap, leverage, and execution delay. Review the Report, Equity graph, and Journal.
5. Compare the EA tester with the Python backtest before any forward demo trial. Backtests are not a guarantee of future performance.

## Python backtest

From a Python environment with `MetaTrader5`, `numpy`, and `pandas` installed:

```powershell
python backtest_xau_v2.py --mt5 --symbol XAUUSD --tf M15 --bars 120000
```

For a separate dataset, use `--csv path.csv` or `--parquet path.parquet`. The current script reports in-sample and out-of-sample performance; selecting settings using the same out-of-sample results still creates selection bias. Do not deploy a parameter set unless it survives genuinely untouched forward data and realistic transaction costs.

## Known research status

The previously shared history had no strategy passing the project's IS/OOS consistency gate. A subsequent MT5 real-tick run of the EA reported PF 0.93, net loss USD 255 on USD 3,000, and 16.28% relative equity drawdown. The current EA changes are therefore for controlled research and safety, not a claim of profitability. MetaEditor compilation and a fresh tester run are still required after changes.
