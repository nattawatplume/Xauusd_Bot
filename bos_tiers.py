"""
bos_tiers.py - ตรวจว่า edge ของ BOS (Break of Structure) กระจุกอยู่ที่ระดับ volume ไหน
ใช้ยืนยันกับข้อมูลโบรกเกอร์ของคุณเอง  (ต้องวางไว้โฟลเดอร์เดียวกับ backtest_xau_v2.py)

    python bos_tiers.py --mt5 --symbol XAUUSD --bars 50000 > tiers.txt
    python bos_tiers.py --parquet xauusd_m1_full.parquet

แบ่งสัญญาณเป็นช่วง volume (เท่าของค่าเฉลี่ย 20 แท่ง) แล้วดูผลแยกกัน IS (ก่อน 2023) กับ OOS (หลัง 2023)
ช่วงที่ "IS และ OOS เป็นบวกทั้งคู่" คือช่วงที่น่าเชื่อถือ ช่วงที่ไม่สม่ำเสมอให้ถือว่าเป็นแค่สัญญาณรบกวน
"""
import argparse
import numpy as np
import backtest_xau_v2 as b


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mt5", action="store_true")
    src.add_argument("--parquet")
    src.add_argument("--csv")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--bars", type=int, default=50000)
    ap.add_argument("--point", type=float, default=0.001)
    ap.add_argument("--split", default="2023-01-01")
    ap.add_argument("--slip", type=float, default=0.10)
    a = ap.parse_args()

    point = a.point
    if a.mt5:
        df, point = b.load_mt5(a.symbol, "H1", a.bars)
    elif a.parquet:
        df = b.resample(b.load_parquet(a.parquet), "1h")
    else:
        df = b.resample(b.load_csv(a.csv), "1h")
    df = df.dropna().reset_index(drop=True)

    atr_s = b.atr(df)
    trend = b.htf_trend(df, "1h")
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    spr = df["spread"].values * point
    split = int(np.searchsorted(df["time"].values, np.datetime64(a.split)))
    yrs = (df["time"].iloc[-1] - df["time"].iloc[0]).days / 365.25
    vr = (df["tick_volume"] / df["tick_volume"].rolling(20).mean()).values
    sig, sl = b.strat_bos_vol(df, atr_s, trend, 1.0, True)       # ปล่อยกว้างสุด แล้วแยกช่วงเอง
    sig, sl = np.asarray(sig), np.asarray(sl, float)

    print(f"ข้อมูล {len(df)} แท่ง H1  {df['time'].iloc[0]} -> {df['time'].iloc[-1]}  ({yrs:.1f} ปี)")
    edges = [1.0, 1.2, 1.5, 2.0, 99]
    for rr in (2.0, 3.0):
        ti, R, rk = b.simulate(o, h, l, c, spr, sig, sl, atr_s.values, rr, 0.8, 3.0, 24, a.slip)
        f = vr[ti]
        print(f"\n--- RR {rr} : แยกตามระดับ volume (เทรนด์ H1 ตรงทิศ) ---")
        for lo, hi in zip(edges[:-1], edges[1:]):
            sel = (f >= lo) & (f < hi)
            ri, ro = R[sel & (ti < split)], R[sel & (ti >= split)]
            lab = f"{lo}-{hi}" if hi < 99 else f">={lo}"
            print(f" vol {lab:8s} ไม้/ปี={sel.sum() / yrs:4.0f} | IS n={len(ri):3d} exp={(ri.mean() if len(ri) else 0):+.3f}"
                  f" | OOS n={len(ro):3d} exp={(ro.mean() if len(ro) else 0):+.3f}")
        A = f >= 2.0
        B = (f >= 1.5) & (f < 2.0)
        for nm, w in (("Tier A เท่านั้น", 0.0), ("Tier A + 0.25 x Tier B", 0.25)):
            wt = np.where(A, 1.0, np.where(B, w, 0.0))
            for part, m in (("IS", ti < split), ("OOS", ti >= split)):
                net = (R * wt)[m].sum()
                span = (split if part == "IS" else len(df) - split) / len(df) * yrs
                print(f"   {nm:24s} {part:3s}: กำไรสุทธิ {net:+6.1f}R (หน่วยเสี่ยงของ Tier A) = {net / span:+.1f}R/ปี")


if __name__ == "__main__":
    main()
