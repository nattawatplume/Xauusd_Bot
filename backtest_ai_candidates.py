"""
backtest_ai_candidates.py - วัดว่า "ตัวเลือกเทคนิค" ที่ Cloud AI ใช้เป็นฐานตัดสินใจ มี edge จริงหรือไม่

ใช้ฟังก์ชัน MarketAnalyzer._technical_candidates ตัวเดียวกับที่รันจริง (ไม่ได้เขียนกฎซ้ำ)
แล้วจำลองการเข้าไม้แบบ EA: เข้าราคาเปิดแท่งถัดไป, SL = ATR x stop_atr, TP = SL x target_r,
ถือไม่เกิน max_hold แท่ง, ชน SL/TP ในแท่งเดียวกันถือว่าแพ้ (มองแง่ร้าย), หัก spread จริงของแต่ละแท่ง

AI (LLM) ทำได้แค่ "ตัดไม้ทิ้ง" จากชุดนี้ ถ้าชุดนี้เองติดลบหลังหักต้นทุน AI ต้องคัดแม่นมากจึงจะพลิกเป็นบวก

    python backtest_ai_candidates.py --mt5 --symbol XAUUSD --bars 100000
    python backtest_ai_candidates.py --csv xau_m5.csv
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_xau_v2 as b

sys.path.insert(0, str(Path(__file__).resolve().parent / "cloud_ai_trader"))
from brain.market_analyzer import MarketAnalyzer  # noqa: E402


def wilder_adx(df, n=14):
    h, l, c = df["high"], df["low"], df["close"]
    up, dn = h.diff(), -l.diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    a = 1.0 / n
    atr_w = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pd.Series(plus, index=df.index).ewm(alpha=a, adjust=False).mean() / atr_w
    mdi = 100 * pd.Series(minus, index=df.index).ewm(alpha=a, adjust=False).mean() / atr_w
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=a, adjust=False).mean()


def build_features(m5):
    m5 = m5.copy().reset_index(drop=True)
    m5["atr"] = b.atr(m5, 14)
    m5["ema9"] = b.ema(m5["close"], 9)
    m5["ema21"] = b.ema(m5["close"], 21)
    m15 = b.resample(m5[["time", "open", "high", "low", "close", "tick_volume", "spread"]], "15min").dropna()
    m15 = m15.reset_index(drop=True)
    m15["ema20"] = b.ema(m15["close"], 20)
    m15["ema50"] = b.ema(m15["close"], 50)
    m15["adx"] = wilder_adx(m15, 14)
    # EA ใช้แท่ง M15 ก่อนหน้าแท่งที่บรรจุแท่งสัญญาณ M5 (ปิดสมบูรณ์แล้ว)
    m15["avail"] = m15["time"] + pd.Timedelta(minutes=15)
    key = m5["time"].dt.floor("15min")
    m15i = m15.set_index("avail")[["ema20", "ema50", "adx"]]
    m5 = m5.join(m15i.reindex(key).reset_index(drop=True))
    return m5


def find_signals(m5, analyzer):
    o, h, l, c = (m5[k].values for k in ("open", "high", "low", "close"))
    sig = np.zeros(len(m5), dtype=int)
    setup = np.array([""] * len(m5), dtype=object)
    for i in range(60, len(m5) - 1):
        row = m5.iloc[i]
        if not np.isfinite(row["adx"]) or not np.isfinite(row["atr"]):
            continue
        candles = [{"o": o[j], "h": h[j], "l": l[j], "c": c[j]} for j in range(i, i - 8, -1)]
        snap = {"adx_m15": row["adx"], "atr_m5": row["atr"], "ema9_m5": row["ema9"], "ema21_m5": row["ema21"],
                "ema20_m15": row["ema20"], "ema50_m15": row["ema50"], "candles_m5": candles}
        cands = analyzer._technical_candidates(snap)
        if cands:
            sig[i] = 1 if cands[0]["side"] == "BUY" else -1
            setup[i] = cands[0]["setup"]
    return sig, setup


def simulate(m5, sig, point, stop_atr, target_r, max_hold, slip):
    o, h, l, c = (m5[k].values for k in ("open", "high", "low", "close"))
    spr = m5["spread"].values * point
    atr_v = m5["atr"].values
    out, i, n = [], 0, len(m5)
    while i < n - 1:
        d = sig[i]
        if d == 0:
            i += 1
            continue
        e = i + 1
        risk = atr_v[i] * stop_atr
        entry = o[e] + (spr[e] + slip if d > 0 else -slip)  # ซื้อที่ ask, ขายที่ bid
        sl, tp = entry - d * risk, entry + d * risk * target_r
        res, j = None, e
        for j in range(e, min(e + max_hold, n)):
            s = spr[j] if d < 0 else 0.0  # ปิด short ต้องซื้อคืนที่ ask
            lo, hi = l[j] + s, h[j] + s
            hit_sl = lo <= sl if d > 0 else hi >= sl
            hit_tp = hi >= tp if d > 0 else lo <= tp
            if hit_sl:
                res = -1.0 - slip / risk
                break
            if hit_tp:
                res = target_r - slip / risk
                break
        if res is None:
            ex = c[j] + (spr[j] if d < 0 else 0.0)
            res = d * (ex - entry) / risk - slip / risk
        out.append((i, res))
        i = j + 1
    return out


def report(name, rows, times, split):
    """Print ALL / IS / OOS stats and return them keyed by part."""
    out = {}
    if not rows:
        print(f"{name:34s} ไม่มีไม้")
        return out
    idx = np.array([r[0] for r in rows])
    R = np.array([r[1] for r in rows])
    for part, m in (("ALL", np.ones(len(R), bool)), ("IS ", times[idx] < split), ("OOS", times[idx] >= split)):
        r = R[m]
        if len(r) == 0:
            continue
        wins, losses = r[r > 0].sum(), -r[r < 0].sum()
        pf = wins / losses if losses > 0 else float("inf")
        eq = np.cumsum(r)
        dd = (np.maximum.accumulate(eq) - eq).max()
        print(f"{name:34s} {part} n={len(r):4d} win={np.mean(r > 0) * 100:5.1f}% "
              f"exp={r.mean():+.3f}R PF={pf:4.2f} net={r.sum():+7.1f}R maxDD={dd:5.1f}R")
        out[part.strip().lower()] = {"n": int(len(r)), "win_rate": round(float(np.mean(r > 0)) * 100, 1),
                                     "expectancy_r": round(float(r.mean()), 3), "profit_factor": round(float(pf), 2),
                                     "net_r": round(float(r.sum()), 1), "max_dd_r": round(float(dd), 1)}
    return out


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mt5", action="store_true")
    src.add_argument("--csv")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--bars", type=int, default=100000)
    ap.add_argument("--point", type=float, default=0.01)
    ap.add_argument("--slip", type=float, default=0.05, help="slippage ต่อด้านเป็นราคา (USD)")
    ap.add_argument("--max-hold", type=int, default=12)
    ap.add_argument("--json", help="เขียนสรุปผลแผนหลัก (SL 1.5ATR TP 1.5R) ให้ dashboard อ่าน")
    a = ap.parse_args()

    if a.mt5:
        m5, point = b.load_mt5(a.symbol, "M5", a.bars)
    else:
        m5, point = b.load_csv(a.csv), a.point
    m5 = build_features(m5.dropna())
    times = m5["time"].values
    split = times[int(len(times) * 2 / 3)]
    print(f"ข้อมูล M5 {len(m5):,} แท่ง {m5['time'].iloc[0]} -> {m5['time'].iloc[-1]} | "
          f"OOS เริ่ม {pd.Timestamp(split)} | spread เฉลี่ย {m5['spread'].mean() * point:.2f} USD")

    sig, setup = find_signals(m5, MarketAnalyzer(None, None))
    print(f"ตัวเลือกทั้งหมด {np.count_nonzero(sig):,} (pullback {np.sum(setup == 'pullback'):,}, "
          f"breakout {np.sum(setup == 'breakout'):,})\n")
    for stop_atr in (1.0, 1.5):
        for target_r in (1.0, 1.5, 2.0):
            for sname, mask in (("all", setup != ""), ("pullback", setup == "pullback"), ("breakout", setup == "breakout")):
                s = np.where(mask, sig, 0)
                rows = simulate(m5, s, point, stop_atr, target_r, a.max_hold, a.slip)
                report(f"SL {stop_atr}ATR TP {target_r}R {sname}", rows, times, split)
            print()

    if a.json:
        base = report("summary SL 1.5ATR TP 1.5R", simulate(m5, sig, point, 1.5, 1.5, a.max_hold, a.slip), times, split)
        free = m5.assign(spread=0)
        gross = report("summary no cost", simulate(free, sig, point, 1.5, 1.5, a.max_hold, 0.0), times, split)
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "symbol": a.symbol, "bars": int(len(m5)),
            "start": str(m5["time"].iloc[0]), "end": str(m5["time"].iloc[-1]), "oos_start": str(pd.Timestamp(split)),
            "avg_spread": round(float(m5["spread"].mean() * point), 3), "slippage": a.slip,
            "plan": "SL 1.5xATR, TP 1.5R, max 12 bars", "net": base, "gross": gross,
        }
        Path(a.json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"เขียนสรุปแล้ว: {a.json}")


if __name__ == "__main__":
    main()
