"""
backtest_xau_v2.py - คัดกลยุทธ์ XAUUSD แบบ "SL ตามโครงสร้างราคา" (ไม่ผูกกับเงินดอลลาร์)

ต่างจาก v1:
 * SL มาจาก price action / โครงสร้าง (swing high-low, กรอบเอเชีย, แท่งเทียนสัญญาณ) + buffer ตาม ATR
   ระยะ SL กว้าง/แคบเกิน (นอกช่วง min-atr..max-atr เท่าของ ATR) -> แคบเกินให้ขยายเป็น min, กว้างเกินให้ข้ามไม้
 * ใช้ volume (tick volume) เป็นตัวกรองยืนยัน
 * ใช้ spread จริงจากข้อมูลแต่ละแท่ง + slippage
 * ไม่มีเพดานต่อวัน ไม่มีเพดานเงิน (แค่รายงานขนาดความเสี่ยงเป็นดอลลาร์ให้ดู)
 * แบ่ง IS / OOS ตามวันที่ และมีตารางผลรายปี เพื่อดูว่ากลยุทธ์สม่ำเสมอหรือแค่โชคดีบางช่วง

รัน:
    python backtest_xau_v2.py --mt5 --tf M15 --bars 120000          # ดึงจาก MT5 ของคุณ
    python backtest_xau_v2.py --parquet xauusd_m1_full.parquet --tf M15
    python backtest_xau_v2.py --csv data.csv --tf M15               # time,open,high,low,close[,tick_volume,spread]
สำคัญ: ยิ่งข้อมูลย้อนหลังยาว ผลยิ่งเชื่อถือได้ (หลายปี หลายสภาพตลาด)
"""
import argparse
import itertools
import sys
import numpy as np
import pandas as pd

TF_RULE = {"M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h"}


# ------------------------------------------------------------------ โหลดข้อมูล
def load_parquet(path):
    df = pd.read_parquet(path).reset_index()
    t = pd.to_datetime(df["time"])
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_convert("UTC").dt.tz_localize(None)
    df["time"] = t
    return df[["time", "open", "high", "low", "close", "tick_volume", "spread"]]


def load_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    df["time"] = pd.to_datetime(df["time"])
    if "tick_volume" not in df:
        df["tick_volume"] = 1
    if "spread" not in df:
        df["spread"] = 0
    return df[["time", "open", "high", "low", "close", "tick_volume", "spread"]]


def load_mt5(symbol, tf, bars):
    import MetaTrader5 as mt5
    tfs = {"M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1}
    if not mt5.initialize(timeout=15000):
        raise SystemExit(f"เชื่อมต่อ MT5 ไม่ได้: {mt5.last_error()}")
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            similar = mt5.symbols_get(group="*XAU*") or ()
            names = ", ".join(s.name for s in similar[:12]) or "ไม่พบ symbol ที่มี XAU"
            raise SystemExit(f"ไม่พบ symbol '{symbol}' ใน MT5 นี้: {mt5.last_error()} | ตัวอย่าง symbol: {names}")
        if not info.visible and not mt5.symbol_select(symbol, True):
            raise SystemExit(f"เลือก symbol '{symbol}' ไม่ได้: {mt5.last_error()}")
        rates = mt5.copy_rates_from_pos(symbol, tfs[tf], 0, bars)
        err = mt5.last_error()
        if rates is None or len(rates) == 0:
            raise SystemExit(
                f"MT5 ไม่ส่งแท่งราคา {symbol} {tf}: {err}. "
                "เปิดกราฟ symbol/timeframe นี้ใน MT5 แล้วเลื่อนกราฟไปทางซ้ายให้โหลด history "
                "จากนั้นลองลด --bars เป็น 50000 หรือเช็ก Tools > Options > Charts > Max bars in chart."
            )
        if len(rates) < bars:
            print(f"คำเตือน: ขอ {bars:,} แท่ง แต่ MT5 มีให้ {len(rates):,} แท่ง; ใช้ข้อมูลที่มีและรายงานช่วงวันที่จริง",
                  file=sys.stderr)
        point = info.point
    finally:
        mt5.shutdown()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df[["time", "open", "high", "low", "close", "tick_volume", "spread"]], point


def resample(df, rule):
    g = df.set_index("time").resample(rule, label="left", closed="left")
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), tick_volume=("tick_volume", "sum"),
                spread=("spread", "mean")).dropna()
    return out.reset_index()


# ------------------------------------------------------------------ indicators
def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def htf_trend(df_base, rule="1h", fast=50, slow=200):
    """เทรนด์จากกรอบใหญ่ (+1 ขึ้น / -1 ลง) ใช้เฉพาะแท่ง HTF ที่ 'ปิดแล้ว' เท่านั้น (ไม่แอบมองอนาคต)"""
    h = resample(df_base[["time", "open", "high", "low", "close", "tick_volume", "spread"]], rule)
    tr = np.sign(ema(h["close"], fast) - ema(h["close"], slow))
    delta = pd.Timedelta(rule if rule != "1h" else "1h")
    s = pd.Series(tr.values, index=h["time"] + delta)          # ใช้ได้หลังแท่ง HTF ปิด
    s = s[~s.index.duplicated()]
    return s.reindex(df_base["time"], method="ffill").fillna(0).values


# ------------------------------------------------------------------ กลยุทธ์ : คืน (sig, sl)
def _first_per_day(sig, day):
    s = pd.Series(sig)
    nz = s != 0
    first = nz & (nz.groupby(day.values).cumsum() == 1)
    return s.where(first, 0).values


def session_levels(df, a0, a1):
    day = df["time"].dt.normalize()
    hr = df["time"].dt.hour
    asia = (hr >= a0) & (hr < a1)
    hi = df["high"].where(asia).groupby(day).transform("max")
    lo = df["low"].where(asia).groupby(day).transform("min")
    return hi, lo, day, hr


def vol_ok(df, mult):
    if mult <= 0:
        return pd.Series(True, index=df.index)
    return df["tick_volume"] > mult * df["tick_volume"].rolling(20).mean()


def strat_session_bo(df, atr_s, a0=0, a1=7, end=12, sl_mode="mid", vol_mult=0.0, buffer_atr=0.1):
    """เบรกกรอบเอเชียด้วยการปิดแท่งทะลุ + volume ยืนยัน ; SL = กลางกรอบ หรือ ขอบตรงข้าม"""
    hi, lo, day, hr = session_levels(df, a0, a1)
    c = df["close"]
    win = (hr >= a1) & (hr < end)
    v = vol_ok(df, vol_mult)
    up = win & v & (c > hi) & (c.shift(1) <= hi)
    dn = win & v & (c < lo) & (c.shift(1) >= lo)
    sig = _first_per_day(np.where(up, 1, np.where(dn, -1, 0)), day)
    mid = (hi + lo) / 2
    sl_buy = mid if sl_mode == "mid" else lo - buffer_atr * atr_s
    sl_sell = mid if sl_mode == "mid" else hi + buffer_atr * atr_s
    sl = np.where(sig == 1, sl_buy, np.where(sig == -1, sl_sell, np.nan))
    return sig, sl


def strat_session_sweep(df, atr_s, a0=0, a1=7, end=12, vol_mult=0.0):
    """กวาด liquidity : ไส้เทียนทะลุขอบกรอบเอเชียแต่ปิดกลับเข้าในกรอบ -> เข้าสวนทิศที่ถูกกวาด
    SL = ปลายไส้ที่กวาด + buffer"""
    hi, lo, day, hr = session_levels(df, a0, a1)
    h, l, c = df["high"], df["low"], df["close"]
    win = (hr >= a1) & (hr < end)
    v = vol_ok(df, vol_mult)
    sell = win & v & (h > hi) & (c < hi)
    buy = win & v & (l < lo) & (c > lo)
    sig = _first_per_day(np.where(buy, 1, np.where(sell, -1, 0)), day)
    sl = np.where(sig == 1, l - 0.1 * atr_s, np.where(sig == -1, h + 0.1 * atr_s, np.nan))
    return sig, sl


def strat_pullback_pa(df, atr_s, trend, vol_mult=0.0):
    """เทรนด์จาก H1 (EMA50/200) + ราคาย่อแตะ EMA21 + แท่งปฏิเสธราคา (pin bar / engulfing)
    SL = ต่ำสุด/สูงสุดของ 2 แท่งล่าสุด + buffer"""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    e21 = ema(c, 21)
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    lw = np.minimum(o, c) - l
    uw = h - np.maximum(o, c)
    bull_pin = (lw >= 2 * body) & (lw >= 0.5 * rng) & (c >= l + 0.6 * rng)
    bear_pin = (uw >= 2 * body) & (uw >= 0.5 * rng) & (c <= h - 0.6 * rng)
    bull_eng = (c > o) & (c.shift(1) < o.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1))
    bear_eng = (c < o) & (c.shift(1) > o.shift(1)) & (c <= o.shift(1)) & (o >= c.shift(1))
    v = vol_ok(df, vol_mult)
    t = pd.Series(trend, index=df.index)
    buy = (t > 0) & v & (l <= e21 + 0.1 * atr_s) & (c > e21) & (bull_pin | bull_eng)
    sell = (t < 0) & v & (h >= e21 - 0.1 * atr_s) & (c < e21) & (bear_pin | bear_eng)
    sig = np.where(buy, 1, np.where(sell, -1, 0))
    sl = np.where(buy, np.minimum(l, l.shift(1)) - 0.2 * atr_s,
                  np.where(sell, np.maximum(h, h.shift(1)) + 0.2 * atr_s, np.nan))
    return sig, sl


def strat_bos_vol(df, atr_s, trend, vol_mult=1.5, use_trend=True):
    """Break of Structure : ปิดทะลุ swing high/low ล่าสุด (fractal 5 แท่ง) + volume พุ่ง (+ตามเทรนด์ H1)
    SL = swing ฝั่งตรงข้ามล่าสุด + buffer"""
    h, l, c = df["high"], df["low"], df["close"]
    sh = h.where(h == h.rolling(5, center=True).max())
    sl_ = l.where(l == l.rolling(5, center=True).min())
    lvl_hi = sh.shift(2).ffill().shift(1)        # swing ยืนยันหลังผ่านไป 2 แท่ง แล้วใช้ตั้งแต่แท่งถัดไป
    lvl_lo = sl_.shift(2).ffill().shift(1)
    v = vol_ok(df, vol_mult)
    t = pd.Series(trend, index=df.index)
    tb = (t > 0) if use_trend else pd.Series(True, index=df.index)
    ts = (t < 0) if use_trend else pd.Series(True, index=df.index)
    buy = v & tb & (c > lvl_hi) & (c.shift(1) <= lvl_hi) & (lvl_lo < c)
    sell = v & ts & (c < lvl_lo) & (c.shift(1) >= lvl_lo) & (lvl_hi > c)
    sig = np.where(buy, 1, np.where(sell, -1, 0))
    sl = np.where(buy, lvl_lo - 0.1 * atr_s, np.where(sell, lvl_hi + 0.1 * atr_s, np.nan))
    return sig, sl


def strat_daytrade_combo(df, atr_s, trend, bos_vol=2.0, pullback_vol=1.2):
    """BOS entries first, then H1-trend EMA21 rejection pullbacks for extra setups."""
    bos_sig, bos_sl = strat_bos_vol(df, atr_s, trend, bos_vol, use_trend=False)
    pb_sig, pb_sl = strat_pullback_pa(df, atr_s, trend, pullback_vol)
    sig = np.where(bos_sig != 0, bos_sig, pb_sig)
    sl = np.where(bos_sig != 0, bos_sl, pb_sl)
    return sig, sl


def strat_ema_cross(df, atr_s):
    """กลยุทธ์เดิม (baseline) EMA9/21 ตัดกัน SL = 1.5xATR"""
    c = df["close"]
    f, s = ema(c, 9), ema(c, 21)
    buy = (f.shift(1) <= s.shift(1)) & (f > s)
    sell = (f.shift(1) >= s.shift(1)) & (f < s)
    sig = np.where(buy, 1, np.where(sell, -1, 0))
    sl = np.where(buy, c - 1.5 * atr_s, np.where(sell, c + 1.5 * atr_s, np.nan))
    return sig, sl


# ------------------------------------------------------------------ ตัวจำลอง
def simulate(o, h, l, c, spr, sig, slarr, atr_arr, rr, min_atr, max_atr, max_hold, slip,
             be_r=0.0, be_min_bars=2, be_off_atr=0.1):
    n = len(c)
    idx = np.flatnonzero(sig != 0)
    ti, R, risk_px = [], [], []
    nxt = 0
    for i in idx:
        if i < nxt or i + 1 >= n or np.isnan(atr_arr[i]) or np.isnan(slarr[i]):
            continue
        d = int(sig[i])
        e = o[i + 1]
        risk = d * (e - slarr[i])
        if risk <= 0:
            continue
        a = atr_arr[i]
        if risk < min_atr * a:
            risk = min_atr * a
        if risk > max_atr * a:
            continue
        sl_cur = e - d * risk
        tp = e + d * risk * rr
        be_done = be_r <= 0
        end = min(n - 1, i + max_hold)
        exit_p, j = None, end
        for j in range(i + 1, end + 1):
            if d == 1:
                if l[j] <= sl_cur: exit_p = sl_cur; break
                if h[j] >= tp: exit_p = tp; break
            else:
                if h[j] >= sl_cur: exit_p = sl_cur; break
                if l[j] <= tp: exit_p = tp; break
            if not be_done and (j - i) >= be_min_bars:
                fav = (h[j] - e) if d == 1 else (e - l[j])
                if fav >= be_r * risk:
                    sl_cur = e + d * be_off_atr * a
                    be_done = True
        if exit_p is None:
            exit_p = c[end]; j = end
        cost = spr[i + 1] + slip
        R.append((d * (exit_p - e) - cost) / risk)
        ti.append(i)
        risk_px.append(risk)
        nxt = j + 1
    return np.array(ti, dtype=int), np.array(R), np.array(risk_px)


def stats(R):
    if len(R) == 0:
        return dict(n=0, win=0, pf=0, exp=0, net=0, dd=0)
    w, ls = R[R > 0].sum(), -R[R < 0].sum()
    eq = np.cumsum(R)
    return dict(n=len(R), win=(R > 0).mean() * 100, pf=(w / ls if ls > 0 else np.inf),
                exp=R.mean(), net=R.sum(), dd=(np.maximum.accumulate(eq) - eq).max())


def fmt(s):
    return (f"n={s['n']:5d} win={s['win']:5.1f}% PF={s['pf']:5.2f} "
            f"exp={s['exp']:+.3f}R net={s['net']:+7.1f}R maxDD={s['dd']:5.1f}R")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mt5", action="store_true")
    src.add_argument("--parquet")
    src.add_argument("--csv")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M15", choices=list(TF_RULE))
    ap.add_argument("--bars", type=int, default=120000)
    ap.add_argument("--point", type=float, default=0.001, help="ขนาด point (parquet Exness = 0.001, FBS 2 หลัก = 0.01)")
    ap.add_argument("--split", default=None, help="วันที่แบ่ง IS / OOS; ไม่ระบุจะแบ่งตามลำดับเวลา 70/30")
    ap.add_argument("--slip", type=float, default=0.10, help="slippage ต่อไม้ (USD)")
    ap.add_argument("--min-atr", type=float, default=1.0)
    ap.add_argument("--max-atr", type=float, default=3.0)
    ap.add_argument("--max-hold-hours", type=float, default=8)
    ap.add_argument("--min-is-trades", type=int, default=100)
    ap.add_argument("--asia", default="1,9,15", help="ชั่วโมง เริ่ม,จบกรอบเอเชีย,จบช่วงเทรด (เวลาในข้อมูล; ตั้งให้ตรงกับ EA)")
    ap.add_argument("--be-r", type=float, default=1.0)
    ap.add_argument("--balance", type=float, default=100.0, help="ใช้รายงานขนาดความเสี่ยงที่ 0.01 lot เท่านั้น")
    a = ap.parse_args()

    point = a.point
    if a.mt5:
        df, point = load_mt5(a.symbol, a.tf, a.bars)
    elif a.parquet:
        df = resample(load_parquet(a.parquet), TF_RULE[a.tf])
    else:
        raw = load_csv(a.csv)
        df = resample(raw, TF_RULE[a.tf]) if a.tf != "M1" else raw
    df = df.dropna().reset_index(drop=True)
    a0, a1, a_end = (int(x) for x in a.asia.split(","))

    print(f"ข้อมูล {len(df)} แท่ง {a.tf}  {df['time'].iloc[0]} -> {df['time'].iloc[-1]}")
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    spr = df["spread"].values * point
    atr_s = atr(df)
    atr_arr = atr_s.values
    bars_per_hour = {"M5": 12, "M15": 4, "M30": 2, "H1": 1}[a.tf]
    max_hold = int(a.max_hold_hours * bars_per_hour)
    trend = htf_trend(df, "1h")

    if a.split:
        split_t = pd.Timestamp(a.split)
        split = int(np.searchsorted(df["time"].values, split_t.to_datetime64()))
        split_label = str(split_t.date())
    else:
        split = int(len(df) * 0.7)
        split_label = str(df["time"].iloc[split].date())
    print(f"IS: ก่อน {split_label} ({split} แท่ง)   OOS: ตั้งแต่ {split_label} ({len(df) - split} แท่ง)")
    print(f"spread มัธยฐานในข้อมูล {np.nanmedian(spr):.2f}$ + slippage {a.slip:.2f}$ ต่อไม้ | "
          f"SL ถูกจำกัดช่วง {a.min_atr}-{a.max_atr} x ATR | ไม่มีเพดานไม้ต่อวัน")

    # ---- รายการ variant ของแต่ละกลยุทธ์
    S = {}
    S["EMA_CROSS (เดิม)"] = [("base", lambda: strat_ema_cross(df, atr_s))]
    S["SESSION_BO (structural SL=opp)"] = [
        (f"vol>{v}", (lambda v=v: strat_session_bo(df, atr_s, a0, a1, a_end,
                                                    "opp", v, buffer_atr=0.1)))
        for v in [0.0, 1.3]
    ]
    S["SESSION_SWEEP"] = [(f"vol>{v}", (lambda v=v: strat_session_sweep(df, atr_s, a0, a1, a_end, v)))
                          for v in [0.0, 1.3]]
    S["PULLBACK_PA (H1 trend)"] = [(f"vol>{v}", (lambda v=v: strat_pullback_pa(df, atr_s, trend, v)))
                                   for v in [0.0, 1.2]]
    S["DAYTRADE_COMBO"] = [
        (f"BOS vol>{bv}, pullback vol>{pv}",
         (lambda bv=bv, pv=pv: strat_daytrade_combo(df, atr_s, trend, bv, pv)))
        for bv, pv in [(2.0, 1.2), (1.5, 1.2)]
    ]
    S["BOS_VOL (H1 trend)"] = [(f"vol>{v} trend={t}", (lambda v=v, t=t: strat_bos_vol(df, atr_s, trend, v, t)))
                               for v, t in itertools.product([1.0, 1.5, 2.0], [True, False])]

    rr_grid = [1.5, 2.0, 3.0]
    summary = []
    years = df["time"].dt.year.values

    for name, variants in S.items():
        best = None
        for label, fn in variants:
            sig, sl = fn()
            sig = np.asarray(sig)
            for rr in rr_grid:
                ti, R, rk = simulate(o, h, l, c, spr, sig, np.asarray(sl, dtype=float), atr_arr, rr,
                                     a.min_atr, a.max_atr, max_hold, a.slip)
                s_is = stats(R[ti < split])
                if s_is["n"] >= a.min_is_trades and (best is None or s_is["exp"] > best["s_is"]["exp"]):
                    best = dict(label=label, rr=rr, sig=sig, sl=np.asarray(sl, dtype=float), ti=ti, R=R, rk=rk, s_is=s_is)
        if best is None:
            print(f"\n=== {name}: ไม้ใน IS น้อยกว่า {a.min_is_trades} ข้าม ===")
            continue
        ti, R, rk = best["ti"], best["R"], best["rk"]
        s_oos = stats(R[ti >= split])
        print(f"\n=== {name}  [เลือกจาก IS: {best['label']}, RR={best['rr']}] ===")
        print("  IS  :", fmt(best["s_is"]))
        print("  OOS :", fmt(s_oos))
        oos_mask = ti >= split
        if oos_mask.any():
            oos_times = df.loc[ti[oos_mask], "time"].reset_index(drop=True)
            oos_returns = R[oos_mask]
            weeks = max((df["time"].iloc[-1] - df["time"].iloc[split]).days / 7, 1 / 7)
            monthly = pd.DataFrame({"time": oos_times, "R": oos_returns}).set_index("time")["R"].resample("MS").sum()
            all_months = pd.date_range(df["time"].iloc[split].to_period("M").to_timestamp(),
                                       df["time"].iloc[-1].to_period("M").to_timestamp(), freq="MS")
            monthly = monthly.reindex(all_months, fill_value=0)
            print(f"  OOS cadence: {len(oos_returns) / weeks:.2f} trades/week, "
                  f"active {oos_times.dt.date.nunique()} days, positive months "
                  f"{int((monthly > 0).sum())}/{len(monthly)}")

        # ผลรายปี
        yr = years[ti]
        row = []
        pos_years = 0
        ny = 0
        for y in sorted(set(yr)):
            ry = R[yr == y]
            if len(ry) >= 5:
                ny += 1
                pos_years += ry.sum() > 0
            row.append(f"{y}:{ry.sum():+.0f}R({len(ry)})")
        print("  รายปี:", "  ".join(row))

        # BE
        ti2, R2, _ = simulate(o, h, l, c, spr, best["sig"], best["sl"], atr_arr, best["rr"],
                              a.min_atr, a.max_atr, max_hold, a.slip, be_r=a.be_r)
        s_oos2 = stats(R2[ti2 >= split])
        print(f"  +BE {a.be_r}R OOS:", fmt(s_oos2),
              "-> BE", "ช่วย" if s_oos2["exp"] > s_oos["exp"] and s_oos2["pf"] >= s_oos["pf"] else "ไม่ช่วย")

        # ขนาด SL เป็นดอลลาร์ (รายงานเฉพาะช่วง OOS ไว้ดูเฉยๆ ที่ 0.01 lot = 1 oz)
        rko = rk[ti >= split]
        if len(rko):
            q = np.percentile(rko, [25, 50, 75])
            print(f"  [ข้อมูลประกอบ] SL ช่วง OOS ที่ 0.01 lot: 25%={q[0]:.1f}$ มัธยฐาน={q[1]:.1f}$ 75%={q[2]:.1f}$ "
                  f"(มัธยฐาน = {q[1] / a.balance * 100:.1f}% ของ {a.balance:.0f}$)")
        summary.append((name, best["label"], best["rr"], s_oos, best["s_is"], pos_years, ny))

    print("\n================ จัดอันดับด้วยผล OOS ================")
    print("เกณฑ์ผ่าน: OOS exp>+0.05R, PF>1.15, n>=60, IS exp>0 และปีที่กำไร >= 60%")
    for name, label, rr, so, si, py, ny in sorted(summary, key=lambda x: -x[3]["exp"]):
        ok = so["exp"] > 0.05 and so["pf"] > 1.15 and so["n"] >= 60 and si["exp"] > 0 and ny > 0 and py / ny >= 0.6
        print(f"{name:24s} OOS exp={so['exp']:+.3f}R PF={so['pf']:4.2f} n={so['n']:5d} | "
              f"IS exp={si['exp']:+.3f}R | ปีกำไร {py}/{ny} -> {'ผ่าน' if ok else 'ไม่ผ่าน'}")


if __name__ == "__main__":
    main()
