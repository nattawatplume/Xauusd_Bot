import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

# =============================
# ตั้งค่าหลัก
# =============================
SYMBOL    = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M15
LOT_SIZE  = 0.01
RR        = 1.0
MAGIC     = 234567  # หมายเลขประจำ bot (ห้ามซ้ำกับ EA อื่น)

def connect():
    if not mt5.initialize():
        print(" เชื่อมต่อ MT5 ไม่ได้:", mt5.last_error())
        return False
    print(" เชื่อมต่อ MT5 สำเร็จ")
    return True

def get_candles(n=50):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, n)
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df

def calc_ema(df, period):
    return df["close"].ewm(span=period, adjust=False).mean()

def get_signal(df):
    df["ema9"]  = calc_ema(df, 9)
    df["ema21"] = calc_ema(df, 21)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if prev["ema9"] < prev["ema21"] and last["ema9"] > last["ema21"]:
        return "BUY"
    elif prev["ema9"] > prev["ema21"] and last["ema9"] < last["ema21"]:
        return "SELL"
    return "WAIT"

def calc_sl_tp(signal, ask, bid):
    df = get_candles(10)
    avg_range   = (df["high"] - df["low"]).mean()
    sl_distance = round(avg_range, 2)
    tp_distance = round(sl_distance * RR, 2)
    if signal == "BUY":
        return ask, round(ask - sl_distance, 2), round(ask + tp_distance, 2)
    else:
        return bid, round(bid + sl_distance, 2), round(bid - tp_distance, 2)

def has_open_order():
    """เช็คว่ามี order ของ bot เปิดอยู่แล้วไหม"""
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions:
        for p in positions:
            if p.magic == MAGIC:
                return True
    return False

def send_order(signal, entry, sl, tp):
    """ส่ง order เข้า MT5 พร้อม SL และ TP"""

    order_type = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action"   : mt5.TRADE_ACTION_DEAL,
        "symbol"   : SYMBOL,
        "volume"   : LOT_SIZE,
        "type"     : order_type,
        "price"    : entry,
        "sl"       : sl,
        "tp"       : tp,
        "magic"    : MAGIC,
        "comment"  : "XAU_BOT",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f" ส่ง Order สำเร็จ!")
        print(f"   Ticket : {result.order}")
        print(f"   Type   : {signal}")
        print(f"   Entry  : {entry}")
        print(f"   SL     : {sl}")
        print(f"   TP     : {tp}")
        return result.order
    else:
        print(f" ส่ง Order ไม่ได้: {result.retcode} - {result.comment}")
        return None

def check_and_trade():
    """ฟังก์ชันหลัก เรียกทุก 15 นาที"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] กำลังวิเคราะห์ XAUUSD M15...")

    # เช็คว่ามี order เปิดอยู่แล้วไหม
    if has_open_order():
        print(" มี order เปิดอยู่แล้ว รอปิดก่อน")
        return

    df     = get_candles(50)
    signal = get_signal(df)
    tick   = mt5.symbol_info_tick(SYMBOL)

    print(f"EMA9  : {df['ema9'].iloc[-1]:.2f}")
    print(f"EMA21 : {df['ema21'].iloc[-1]:.2f}")
    print(f"สัญญาณ: {signal}")

    if signal == "WAIT":
        print("ยังไม่มีสัญญาณ รอรอบถัดไป...")
        return

    entry, sl, tp = calc_sl_tp(signal, tick.ask, tick.bid)
    print(f"Entry : {entry}")
    print(f"SL    : {sl}  (ห่าง {round(abs(entry-sl),2)}$)")
    print(f"TP    : {tp}  (ห่าง {round(abs(tp-entry),2)}$)")

    send_order(signal, entry, sl, tp)

# =============================
# รันทดสอบครั้งเดียวก่อน
# =============================
if connect():
    check_and_trade()
    mt5.shutdown()