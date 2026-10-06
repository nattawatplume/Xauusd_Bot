//+------------------------------------------------------------------+
//| XAU_Pro_EA.mq5                                                   |
//| Experimental XAUUSD day-trading EA                               |
//|                                                                  |
//| วิธีใช้: คัดลอกไปไว้ที่ MQL5/Experts แล้วกด F7 compile ใน MetaEditor  |
//| ทดสอบ: MT5 > Strategy Tester > Model = "Every tick based on      |
//|        real ticks" > Symbol XAUUSD > ช่วงเวลา >= 2 ปี              |
//+------------------------------------------------------------------+
#property copyright "Nattawat"
#property version   "1.70"
#property strict

#include <Trade/Trade.mqh>
CTrade trade;

enum ENUM_STRAT
{
   STRAT_AUTO_ADAPTIVE    = 0,   // โหมดทดลองปรับตามสภาวะตลาด
   STRAT_TREND_PULLBACK   = 1,   // เทรนด์ + RSI ย่อ/เด้ง
   STRAT_DONCHIAN         = 2,   // เบรกเอาท์ Donchian + ADX
   STRAT_SESSION_BREAKOUT = 3,   // เบรกกรอบเอเชีย
   STRAT_EMA_CROSS        = 4,   // EMA ตัดกัน (กลยุทธ์เดิม ไว้เทียบ)
   STRAT_ALL_DAY_BOS      = 5,   // BOS + volume; ตรวจสัญญาณได้ทั้งวัน
   STRAT_DAYTRADE_COMBO   = 6,   // BOS, then trend-pullback fallback for more setups
   STRAT_SCALP_PA         = 7,   // Conservative M5 pullback/rejection baseline
   STRAT_SCALP_ACTIVE     = 8    // More frequent M5 pullback + continuation with M15 bias
};

//--- ตั้งค่าทั่วไป
input ENUM_STRAT      Strategy          = STRAT_SCALP_ACTIVE;
input ENUM_TIMEFRAMES TF                = PERIOD_M5;
input long            MagicNumber       = 234567;

//--- risk-based money management; minimum volume can exceed the cap on a $100 account
input double MaxRiskPercent     = 10.0;   // hard per-trade loss cap, including estimated stop loss
input double LotPer100USD       = 0.01;   // $100 equity -> 0.01 lot; actual risk is checked before entry
input double MaxMarginUsePct    = 50.0;   // margin ของไม้นี้ต้องไม่เกิน % ของ free margin
input double SL_ATR_Mult        = 1.0;    // fallback SL = ATR x ค่านี้
input double MaxSL_USD          = 0.0;    // zero disables the absolute price cap
input double RR                 = 1.5;    // fallback target for non-scalp strategies
input int    ATR_Period         = 14;
input double SL_BufferATR       = 0.1;
input double MinRiskATR         = 1.0;
input double MaxRiskATR         = 3.0;
input double SessionVolMult     = 0.0;    // 0=off; match this to the winning backtest variant
input double BOSVolMult         = 2.0;    // candidate variant; not proven profitable out of sample
input double PullbackVolMult    = 1.2;    // volume confirmation for the day-trade pullback leg
input bool   BOSUseH1Trend      = false;  // variant OOS บวกล่าสุดเลือกแบบไม่ใช้ H1 แต่ IS ยังติดลบ
input int    MaxHoldBars        = 12;     // 12 แท่ง M5 = 1 ชั่วโมง
input int    ScalpMaxSLPoints   = 1000;   // scalp entries wider than this are skipped
input double ScalpMinRR         = 1.0;    // skip when nearest structure offers less than this R
input double ScalpMaxRR         = 2.0;    // cap structural target at this R
input double ScalpMinADX        = 18.0;   // skip weak M15 trends; 0 disables this filter
input double ScalpMinTrendGapATR= 0.10;   // M15 EMA20/50 separation as a fraction of ATR; 0 disables
input double ScalpMinSlopeATR   = 0.02;   // M15 EMA20 slope over two closed bars; 0 disables
input double ScalpVolMult       = 1.0;    // require signal-bar tick volume near/above its 20-bar mean
input double ActiveMinADX       = 14.0;   // softer M15 trend strength floor for active mode
input double ActiveTrendGapATR  = 0.05;   // M15 EMA20/50 gap as a fraction of ATR
input double ActiveSlopeATR     = 0.01;   // M15 EMA20 slope over two closed bars
input double ActiveVolMult      = 0.80;   // M5 signal-bar tick volume vs prior 20-bar mean
input double ActiveTouchATR     = 0.35;   // pullback may touch EMA9 or EMA21 within this ATR band
input int    ActiveBreakoutBars = 6;      // allow confirmed continuation close beyond recent range
input bool   EnableRecoverySizing = false; // keep off until the base strategy passes out-of-sample tests
input double RecoveryMultiplier  = 1.20;  // risk grows modestly after each loss
input int    RecoveryMaxSteps     = 2;     // risk cap remains active at every step

//--- Break-even: เลื่อน SL มาหน้าทุน "หลังกำไรถึงระดับหนึ่งและถือมาระยะหนึ่ง"
input bool   EnableBE           = false;   // session breakout backtest ไม่พบว่า BE ช่วยผล OOS
input double BE_TriggerR        = 1.0;    // กำไรต้องถึงกี่เท่าของระยะ SL เดิม (1.0 = กำไรเท่าที่เสี่ยง)
input int    BE_MinBars         = 2;      // ต้องถือมาแล้วอย่างน้อยกี่แท่ง
input int    BE_OffsetPoints    = 20;     // SL ใหม่ = ราคาเข้า + ค่านี้ (กันค่าคอม/สลิป) 20 points = 0.20$

//--- ตัวป้องกัน
input double MaxSpreadPoints    = 40;     // spread เกินนี้ไม่เข้า (40 points = 0.40$ บนทองแบบ 2 หลัก)
input double MaxDailyLossPct    = 1.5;    // daily equity loss stop remains active
input int    MaxTradesPerDay    = 0;      // 0 = no daily trade-count limit
input int    MaxConsecLosses    = 4;      // consecutive losses before a cooldown
input int    PauseHoursAfterLoss= 4;      // cooldown after the loss streak
input double MaxDrawdownPct     = 15.0;   // halt new entries after equity drawdown from peak
input bool   ResetPeakOnInit    = false;  // true = รีเซ็ต peak/สถานะหยุด ตอนโหลด EA (ใช้ครั้งเดียวแล้วปิด)
input int    StartHour          = 0;      // เวลา server ของโบรกเกอร์
input int    EndHour            = 24;     // 24=เทรดได้ถึงวันใหม่ตามเวลา server

//--- Trend pullback / EMA cross
input int    EMA_Fast           = 50;
input int    EMA_Slow           = 200;
input int    RSI_Period         = 14;
input double RSI_BuyLevel       = 40;
input double RSI_SellLevel      = 60;
input int    Cross_Fast         = 9;      // ใช้เมื่อ Strategy = EMA_CROSS
input int    Cross_Slow         = 21;

//--- Donchian
input int    Donchian_Period    = 20;
input int    ADX_Period         = 14;
input double ADX_Min            = 20;

//--- Session breakout (เวลาเซิร์ฟเวอร์ ปรับตามโบรกเกอร์!)
input int    AsiaStartHour      = 1;
input int    AsiaEndHour        = 9;
input int    BreakoutEndHour    = 15;

//--- handles
int hATR, hEmaFast, hEmaSlow, hRSI, hADX, hCrossFast, hCrossSlow;
int hTrendFastH1, hTrendSlowH1, hPullbackEMA, hScalpTrendFast, hScalpTrendSlow;
int hScalpADX, hScalpATR;
datetime lastBarTime   = 0;
int      lastTradeDay  = -1;
double   signalStructSL = 0;
double   signalStructTP = 0;
int      dayKey        = -1;
double   dayStartEquity = 0;

string GVPrefix()
{
   return "XAUEA_" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "_" +
          IntegerToString(MagicNumber) + "_" + _Symbol;
}
string GVPeak() { return GVPrefix() + "_PEAK"; }
string GVHalt() { return GVPrefix() + "_HALT"; }
string GVDailyEquity(int key)
{
   return "XAUEA_DAYEQ_" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)) + "_" +
          IntegerToString(MagicNumber) + "_" + _Symbol + "_" + IntegerToString(key);
}

//+------------------------------------------------------------------+
int OnInit()
{
   if(MaxRiskPercent <= 0 || MaxRiskPercent > 10.0 ||
      RR <= 0 || ATR_Period < 1 || MaxHoldBars < 1 ||
      MinRiskATR <= 0 || MaxRiskATR < MinRiskATR ||
      MaxDailyLossPct <= 0 || MaxDailyLossPct >= 100 ||
      MaxTradesPerDay < 0 || MaxConsecLosses < 1 || PauseHoursAfterLoss < 0 ||
      RecoveryMultiplier < 1.0 || RecoveryMaxSteps < 0 || PullbackVolMult < 0 ||
      LotPer100USD <= 0 || ScalpMaxSLPoints < 1 || ScalpMinRR <= 0 ||
      ScalpMaxRR < ScalpMinRR || ScalpMinADX < 0 || ScalpMinTrendGapATR < 0 ||
      ScalpMinSlopeATR < 0 || ScalpVolMult < 0 || ActiveMinADX < 0 ||
      ActiveTrendGapATR < 0 || ActiveSlopeATR < 0 || ActiveVolMult < 0 ||
      ActiveTouchATR < 0 || ActiveBreakoutBars < 2 ||
      StartHour < 0 || StartHour > 23 || EndHour < 1 || EndHour > 24 || StartHour >= EndHour)
   {
      Print("ค่าตั้งต้นไม่ถูกต้อง: ตรวจ Risk/RR/ATR/เวลา/Recovery ก่อนเริ่ม EA");
      return INIT_PARAMETERS_INCORRECT;
   }

   hATR       = iATR(_Symbol, TF, ATR_Period);
   hEmaFast   = iMA(_Symbol, TF, EMA_Fast, 0, MODE_EMA, PRICE_CLOSE);
   hEmaSlow   = iMA(_Symbol, TF, EMA_Slow, 0, MODE_EMA, PRICE_CLOSE);
   hRSI       = iRSI(_Symbol, TF, RSI_Period, PRICE_CLOSE);
   hADX       = iADX(_Symbol, TF, ADX_Period);
   hCrossFast = iMA(_Symbol, TF, Cross_Fast, 0, MODE_EMA, PRICE_CLOSE);
   hCrossSlow = iMA(_Symbol, TF, Cross_Slow, 0, MODE_EMA, PRICE_CLOSE);
   hTrendFastH1 = iMA(_Symbol, PERIOD_H1, EMA_Fast, 0, MODE_EMA, PRICE_CLOSE);
   hTrendSlowH1 = iMA(_Symbol, PERIOD_H1, EMA_Slow, 0, MODE_EMA, PRICE_CLOSE);
   hPullbackEMA = iMA(_Symbol, TF, 21, 0, MODE_EMA, PRICE_CLOSE);
   hScalpTrendFast = iMA(_Symbol, PERIOD_M15, 20, 0, MODE_EMA, PRICE_CLOSE);
   hScalpTrendSlow = iMA(_Symbol, PERIOD_M15, 50, 0, MODE_EMA, PRICE_CLOSE);
   hScalpADX = iADX(_Symbol, PERIOD_M15, ADX_Period);
   hScalpATR = iATR(_Symbol, PERIOD_M15, ATR_Period);

   if(hATR==INVALID_HANDLE || hEmaFast==INVALID_HANDLE || hEmaSlow==INVALID_HANDLE ||
      hRSI==INVALID_HANDLE || hADX==INVALID_HANDLE || hCrossFast==INVALID_HANDLE ||
      hCrossSlow==INVALID_HANDLE || hTrendFastH1==INVALID_HANDLE || hTrendSlowH1==INVALID_HANDLE ||
      hPullbackEMA==INVALID_HANDLE || hScalpTrendFast==INVALID_HANDLE ||
      hScalpTrendSlow==INVALID_HANDLE || hScalpADX==INVALID_HANDLE ||
      hScalpATR==INVALID_HANDLE)
   {
      Print("สร้าง indicator ไม่สำเร็จ");
      return INIT_FAILED;
   }

   if(ResetPeakOnInit || !GlobalVariableCheck(GVPeak()))
      GlobalVariableSet(GVPeak(), AccountInfoDouble(ACCOUNT_EQUITY));
   if(ResetPeakOnInit) GlobalVariableSet(GVHalt(), 0);

   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(30);
   trade.SetTypeFillingBySymbol(_Symbol);   // เลือกโหมด filling ให้ตรงกับโบรกเกอร์อัตโนมัติ
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   IndicatorRelease(hATR);      IndicatorRelease(hEmaFast); IndicatorRelease(hEmaSlow);
   IndicatorRelease(hRSI);      IndicatorRelease(hADX);
   IndicatorRelease(hCrossFast);IndicatorRelease(hCrossSlow);
   IndicatorRelease(hTrendFastH1); IndicatorRelease(hTrendSlowH1);
   IndicatorRelease(hPullbackEMA);
   IndicatorRelease(hScalpTrendFast); IndicatorRelease(hScalpTrendSlow);
   IndicatorRelease(hScalpADX); IndicatorRelease(hScalpATR);
}

//+------------------------------------------------------------------+
//| อ่านค่า indicator 1 ค่า                                            |
//+------------------------------------------------------------------+
double Buf(int handle, int shift, int bufferIndex = 0)
{
   double a[1];
   if(CopyBuffer(handle, bufferIndex, shift, 1, a) != 1) return EMPTY_VALUE;
   return a[0];
}

bool HasPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         return true;
   }
   return false;
}

//--- ถือนานเกินกำหนด -> ปิด
void ManageTimeExit()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      if((TimeCurrent() - opened) / PeriodSeconds(TF) >= MaxHoldBars)
      {
         ulong ticket = (ulong)PositionGetInteger(POSITION_TICKET);
         bool sent = trade.PositionClose(ticket);
         uint rc = trade.ResultRetcode();
         if(!sent || (rc != TRADE_RETCODE_DONE && rc != TRADE_RETCODE_DONE_PARTIAL))
            PrintFormat("ปิด position ตามเวลาไม่สำเร็จ ticket=%I64u retcode=%u %s",
                        ticket, rc, trade.ResultRetcodeDescription());
      }
   }
}

//+------------------------------------------------------------------+
//| Break-even : เลื่อน SL มาหน้าทุนครั้งเดียว (เช็คทุก tick)              |
//| ใช้ "SL ยังอยู่ฝั่งขาดทุน" เป็นตัวบอกว่ายังไม่เคยเลื่อน -> ไม่ต้องเก็บสถานะ |
//+------------------------------------------------------------------+
void ManageBreakEven()
{
   if(!EnableBE) return;
   double stopLvl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

      ulong    ticket = PositionGetInteger(POSITION_TICKET);
      long     type   = PositionGetInteger(POSITION_TYPE);
      double   open   = PositionGetDouble(POSITION_PRICE_OPEN);
      double   sl     = PositionGetDouble(POSITION_SL);
      double   tp     = PositionGetDouble(POSITION_TP);
      datetime opened = (datetime)PositionGetInteger(POSITION_TIME);
      if(sl == 0) continue;

      bool   isBuy = (type == POSITION_TYPE_BUY);
      double risk  = isBuy ? (open - sl) : (sl - open);
      if(risk <= 0) continue;                                   // SL อยู่หน้าทุนแล้ว = เคยเลื่อนไปแล้ว

      double price  = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double profit = isBuy ? (price - open) : (open - price);
      long   held   = (TimeCurrent() - opened) / PeriodSeconds(TF);

      if(profit < BE_TriggerR * risk) continue;                 // กำไรยังไม่ถึงเกณฑ์
      if(held < BE_MinBars)           continue;                 // ถือยังไม่นานพอ

      double newSL = isBuy ? open + BE_OffsetPoints * _Point : open - BE_OffsetPoints * _Point;
      newSL = NormalizeDouble(newSL, _Digits);

      // SL ใหม่ต้องห่างราคาปัจจุบันตามที่โบรกเกอร์กำหนด
      if(isBuy  && (price - newSL) < stopLvl) continue;
      if(!isBuy && (newSL - price) < stopLvl) continue;

      bool sent = trade.PositionModify(ticket, newSL, tp);
      uint rc = trade.ResultRetcode();
      if(sent && rc == TRADE_RETCODE_DONE)
         PrintFormat("BE: ticket %I64u เลื่อน SL มา %.2f", ticket, newSL);
      else
         PrintFormat("เลื่อน SL เป็น BE ไม่สำเร็จ ticket=%I64u retcode=%u %s",
                     ticket, rc, trade.ResultRetcodeDescription());
   }
}

//+------------------------------------------------------------------+
//| สถิติจากประวัติเทรดของ EA นี้                                       |
//+------------------------------------------------------------------+
int TradesOpenedToday()
{
   datetime now = TimeCurrent();
   MqlDateTime brokerTime;
   TimeToStruct(now, brokerTime);
   brokerTime.hour = 0;
   brokerTime.min = 0;
   brokerTime.sec = 0;
   datetime dayStart = StructToTime(brokerTime);
   if(!HistorySelect(dayStart, now + 60)) return 0;
   int n = 0;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong tk = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != MagicNumber) continue;
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(tk, DEAL_ENTRY) == DEAL_ENTRY_IN) n++;
   }
   return n;
}

// นับแพ้ติดกัน (ไม้ที่ปิดใกล้ทุน เช่น BE ไม่นับว่าแพ้หรือชนะ)
int ConsecLosses(datetime &lastCloseTime)
{
   lastCloseTime = 0;
   int cnt = 0;
   if(!HistorySelect(TimeCurrent() - 14 * 86400, TimeCurrent() + 60)) return 0;
   double scratchTol = AccountInfoDouble(ACCOUNT_BALANCE) * 0.002;   // 0.2% ของทุน

   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong tk = HistoryDealGetTicket(i);
      if(HistoryDealGetInteger(tk, DEAL_MAGIC) != MagicNumber) continue;
      if(HistoryDealGetString(tk, DEAL_SYMBOL) != _Symbol) continue;
      if(HistoryDealGetInteger(tk, DEAL_ENTRY) != DEAL_ENTRY_OUT) continue;

      double p = HistoryDealGetDouble(tk, DEAL_PROFIT) + HistoryDealGetDouble(tk, DEAL_COMMISSION)
               + HistoryDealGetDouble(tk, DEAL_SWAP);
      if(MathAbs(p) < scratchTol) continue;                          // ไม้เสมอตัว ข้าม
      if(lastCloseTime == 0) lastCloseTime = (datetime)HistoryDealGetInteger(tk, DEAL_TIME);
      if(p < 0) cnt++; else break;
   }
   return cnt;
}

//+------------------------------------------------------------------+
//| ตัวกรองก่อนเข้า (เรียกตอนแท่งใหม่)                                   |
//+------------------------------------------------------------------+
bool FiltersOK()
{
   MqlDateTime t;
   TimeToStruct(TimeCurrent(), t);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);

   // 1) Kill-switch: DD จากจุดสูงสุดของ equity
   double peak = GlobalVariableCheck(GVPeak()) ? GlobalVariableGet(GVPeak()) : eq;
   if(eq > peak) { peak = eq; GlobalVariableSet(GVPeak(), peak); }
   if(peak > 0 && eq < peak * (1.0 - MaxDrawdownPct / 100.0))
   {
      if(GlobalVariableGet(GVHalt()) != 1)
         PrintFormat("KILL-SWITCH: equity %.2f ต่ำกว่า peak %.2f เกิน %.1f%% -> หยุดเปิดไม้ใหม่", eq, peak, MaxDrawdownPct);
      GlobalVariableSet(GVHalt(), 1);
   }
   if(GlobalVariableGet(GVHalt()) == 1) return false;

   // 2) ขาดทุนรายวัน
   int key = t.year * 1000 + t.day_of_year;
   if(key != dayKey)
   {
      dayKey = key;
      string gv = GVDailyEquity(key);
      if(GlobalVariableCheck(gv)) dayStartEquity = GlobalVariableGet(gv);
      else
      {
         dayStartEquity = eq;
         GlobalVariableSet(gv, dayStartEquity);
      }
   }
   if(dayStartEquity > 0 && eq < dayStartEquity * (1.0 - MaxDailyLossPct / 100.0)) return false;

   // 3) เวลาและ spread
   if(t.hour < StartHour || t.hour >= EndHour) return false;
   if(SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) > MaxSpreadPoints) return false;

   // 4) จำนวนไม้ต่อวัน และแพ้ติดกัน
   if(MaxTradesPerDay > 0 && TradesOpenedToday() >= MaxTradesPerDay) return false;
   datetime lastClose;
   if(ConsecLosses(lastClose) >= MaxConsecLosses &&
      TimeCurrent() - lastClose < PauseHoursAfterLoss * 3600) return false;

   return true;
}

//+------------------------------------------------------------------+
//| สัญญาณ: +1 ซื้อ / -1 ขาย / 0 ไม่ทำ  (ใช้แท่งที่ปิดแล้ว shift 1,2)      |
//+------------------------------------------------------------------+
int SignalTrendPullback()
{
   double f = Buf(hEmaFast, 1), s = Buf(hEmaSlow, 1);
   double r1 = Buf(hRSI, 1), r2 = Buf(hRSI, 2);
   if(f==EMPTY_VALUE || s==EMPTY_VALUE || r1==EMPTY_VALUE || r2==EMPTY_VALUE) return 0;
   double atr = Buf(hATR, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return 0;
   if(f > s && r2 < RSI_BuyLevel && r1 >= RSI_BuyLevel)
   {
      signalStructSL = MathMin(iLow(_Symbol, TF, 1), iLow(_Symbol, TF, 2)) - SL_BufferATR * atr;
      return 1;
   }
   if(f < s && r2 > RSI_SellLevel && r1 <= RSI_SellLevel)
   {
      signalStructSL = MathMax(iHigh(_Symbol, TF, 1), iHigh(_Symbol, TF, 2)) + SL_BufferATR * atr;
      return -1;
   }
   return 0;
}

int SignalDonchian()
{
   double adx = Buf(hADX, 1, 0);                 // buffer 0 = ค่า ADX หลัก
   if(adx == EMPTY_VALUE || adx < ADX_Min) return 0;
   int ih = iHighest(_Symbol, TF, MODE_HIGH, Donchian_Period, 2);
   int il = iLowest (_Symbol, TF, MODE_LOW,  Donchian_Period, 2);
   if(ih < 0 || il < 0) return 0;
   double hh = iHigh(_Symbol, TF, ih), ll = iLow(_Symbol, TF, il);
   double c1 = iClose(_Symbol, TF, 1);
   if(c1 > hh) return  1;
   if(c1 < ll) return -1;
   return 0;
}

int SignalEmaCross()
{
   double f1 = Buf(hCrossFast, 1), s1 = Buf(hCrossSlow, 1);
   double f2 = Buf(hCrossFast, 2), s2 = Buf(hCrossSlow, 2);
   if(f1==EMPTY_VALUE || s1==EMPTY_VALUE || f2==EMPTY_VALUE || s2==EMPTY_VALUE) return 0;
   if(f2 <= s2 && f1 > s1) return  1;
   if(f2 >= s2 && f1 < s1) return -1;
   return 0;
}

int SignalSessionBreakout()
{
   MqlDateTime sigTime;
   TimeToStruct(iTime(_Symbol, TF, 1), sigTime); // เวลาเปิดของแท่งสัญญาณที่เพิ่งปิด
   if(sigTime.hour < AsiaEndHour || sigTime.hour >= BreakoutEndHour) return 0;
   int today = sigTime.year * 1000 + sigTime.day_of_year;
   if(lastTradeDay == today) return 0;           // วันละ 1 ไม้

   // หา High/Low ของช่วงเอเชียของวันนี้
   double hi = -DBL_MAX, lo = DBL_MAX;
   bool found = false;
   for(int sh = 1; sh < 400; sh++)
   {
      datetime bt = iTime(_Symbol, TF, sh);
      if(bt == 0) break;
      MqlDateTime b;
      TimeToStruct(bt, b);
      if(b.year * 1000 + b.day_of_year != today) break;      // ย้อนจนข้ามวัน
      if(b.hour >= AsiaStartHour && b.hour < AsiaEndHour)
      {
         hi = MathMax(hi, iHigh(_Symbol, TF, sh));
         lo = MathMin(lo, iLow(_Symbol, TF, sh));
         found = true;
      }
   }
   if(!found) return 0;

   double c1 = iClose(_Symbol, TF, 1), c2 = iClose(_Symbol, TF, 2);
   double atr = Buf(hATR, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return 0;
   if(SessionVolMult > 0)
   {
      double volSum = 0;
      for(int k = 1; k <= 20; k++) volSum += (double)iTickVolume(_Symbol, TF, k);
      if(volSum <= 0 || (double)iTickVolume(_Symbol, TF, 1) <= SessionVolMult * volSum / 20.0)
         return 0;
   }
   if(c1 > hi && c2 <= hi)
   {
      signalStructSL = lo - SL_BufferATR * atr;
      return 1;
   }
   if(c1 < lo && c2 >= lo)
   {
      signalStructSL = hi + SL_BufferATR * atr;
      return -1;
   }
   return 0;
}

bool FindSwing(bool isHigh, int fromShift, double &level)
{
   const int maxBack = 400;
   for(int k = fromShift; k <= maxBack; k++)
   {
      double v = isHigh ? iHigh(_Symbol, TF, k) : iLow(_Symbol, TF, k);
      if(v == 0) return false;
      bool ok = true;
      for(int j = k - 2; j <= k + 2; j++)
      {
         if(j == k) continue;
         double w = isHigh ? iHigh(_Symbol, TF, j) : iLow(_Symbol, TF, j);
         if(w == 0) { ok = false; break; }
         if(isHigh ? (w > v) : (w < v)) { ok = false; break; }
      }
      if(ok) { level = v; return true; }
   }
   return false;
}

int SignalAllDayBOS()
{
   double atr = Buf(hATR, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return 0;
   double swingHigh, swingLow;
   if(!FindSwing(true, 4, swingHigh) || !FindSwing(false, 4, swingLow)) return 0;

   double c1 = iClose(_Symbol, TF, 1), c2 = iClose(_Symbol, TF, 2);
   double sum = 0;
   for(int k = 1; k <= 20; k++) sum += (double)iTickVolume(_Symbol, TF, k);
   if(sum <= 0) return 0;
   double avg = sum / 20.0;
   double vol1 = (double)iTickVolume(_Symbol, TF, 1);
   if(vol1 <= BOSVolMult * avg) return 0; // backtest ใช้ volume > ค่าเฉลี่ย x multiplier

   int trend = 0;
   if(BOSUseH1Trend)
   {
      datetime signalTime = iTime(_Symbol, TF, 1);
      int trendShift = iBarShift(_Symbol, PERIOD_H1, signalTime, false) + 1;
      if(trendShift < 1) return 0;
      double fast = Buf(hTrendFastH1, trendShift), slow = Buf(hTrendSlowH1, trendShift);
      if(fast == EMPTY_VALUE || slow == EMPTY_VALUE) return 0;
      trend = (fast > slow) ? 1 : ((fast < slow) ? -1 : 0);
   }

   bool buy = c1 > swingHigh && c2 <= swingHigh && swingLow < c1 &&
              (!BOSUseH1Trend || trend > 0);
   bool sell = c1 < swingLow && c2 >= swingLow && swingHigh > c1 &&
               (!BOSUseH1Trend || trend < 0);
   if(buy)
   {
      signalStructSL = swingLow - SL_BufferATR * atr;
      return 1;
   }
   if(sell)
   {
      signalStructSL = swingHigh + SL_BufferATR * atr;
      return -1;
   }
   return 0;
}

int SignalPullbackPA()
{
   double atr = Buf(hATR, 1), ema21 = Buf(hPullbackEMA, 1);
   if(atr == EMPTY_VALUE || ema21 == EMPTY_VALUE || atr <= 0) return 0;

   datetime signalTime = iTime(_Symbol, TF, 1);
   int trendShift = iBarShift(_Symbol, PERIOD_H1, signalTime, false) + 1;
   if(trendShift < 1) return 0;
   double fast = Buf(hTrendFastH1, trendShift), slow = Buf(hTrendSlowH1, trendShift);
   if(fast == EMPTY_VALUE || slow == EMPTY_VALUE) return 0;
   int trend = (fast > slow) ? 1 : ((fast < slow) ? -1 : 0);

   double o1 = iOpen(_Symbol, TF, 1), c1 = iClose(_Symbol, TF, 1);
   double h1 = iHigh(_Symbol, TF, 1), l1 = iLow(_Symbol, TF, 1);
   double o2 = iOpen(_Symbol, TF, 2), c2 = iClose(_Symbol, TF, 2);
   double h2 = iHigh(_Symbol, TF, 2), l2 = iLow(_Symbol, TF, 2);
   double range = h1 - l1;
   if(range <= 0) return 0;

   double body = MathAbs(c1 - o1);
   double lowerWick = MathMin(o1, c1) - l1;
   double upperWick = h1 - MathMax(o1, c1);
   bool bullPin = lowerWick >= 2.0 * body && lowerWick >= 0.5 * range && c1 >= l1 + 0.6 * range;
   bool bearPin = upperWick >= 2.0 * body && upperWick >= 0.5 * range && c1 <= h1 - 0.6 * range;
   bool bullEngulf = c1 > o1 && c2 < o2 && c1 >= o2 && o1 <= c2;
   bool bearEngulf = c1 < o1 && c2 > o2 && c1 <= o2 && o1 >= c2;

   double volSum = 0;
   for(int k = 1; k <= 20; k++) volSum += (double)iTickVolume(_Symbol, TF, k);
   if(volSum <= 0) return 0;
   double volAverage = volSum / 20.0;
   double vol1 = (double)iTickVolume(_Symbol, TF, 1);
   if(vol1 <= PullbackVolMult * volAverage) return 0;

   bool buy = trend > 0 && l1 <= ema21 + 0.1 * atr && c1 > ema21 && (bullPin || bullEngulf);
   bool sell = trend < 0 && h1 >= ema21 - 0.1 * atr && c1 < ema21 && (bearPin || bearEngulf);
   if(buy)
   {
      signalStructSL = MathMin(l1, l2) - 0.2 * atr;
      return 1;
   }
   if(sell)
   {
      signalStructSL = MathMax(h1, h2) + 0.2 * atr;
      return -1;
   }
   return 0;
}

int SignalDayTradeCombo()
{
   // Prefer volume-confirmed BOS. If there is no breakout, allow a trend pullback.
   int bos = SignalAllDayBOS();
   if(bos != 0) return bos;
   return SignalPullbackPA();
}

int SignalScalpPA()
{
   double atr = Buf(hATR, 1);
   double emaFast = Buf(hCrossFast, 1), emaSlow = Buf(hCrossSlow, 1);
   if(atr == EMPTY_VALUE || atr <= 0 || emaFast == EMPTY_VALUE || emaSlow == EMPTY_VALUE)
      return 0;

   datetime signalTime = iTime(_Symbol, TF, 1);
   int trendShift = iBarShift(_Symbol, PERIOD_M15, signalTime, false) + 1;
   if(trendShift < 1) return 0;
   double trendFast = Buf(hScalpTrendFast, trendShift);
   double trendSlow = Buf(hScalpTrendSlow, trendShift);
   double trendFastOld = Buf(hScalpTrendFast, trendShift + 2);
   double trendATR = Buf(hScalpATR, trendShift);
   double trendADX = Buf(hScalpADX, trendShift, 0);
   if(trendFast == EMPTY_VALUE || trendSlow == EMPTY_VALUE || trendFastOld == EMPTY_VALUE ||
      trendATR == EMPTY_VALUE || trendATR <= 0 || trendADX == EMPTY_VALUE || trendFast == trendSlow)
      return 0;
   if(ScalpMinADX > 0 && trendADX < ScalpMinADX) return 0;
   if(ScalpMinTrendGapATR > 0 && MathAbs(trendFast - trendSlow) / trendATR < ScalpMinTrendGapATR)
      return 0;

   double o1 = iOpen(_Symbol, TF, 1), c1 = iClose(_Symbol, TF, 1);
   double h1 = iHigh(_Symbol, TF, 1), l1 = iLow(_Symbol, TF, 1);
   double o2 = iOpen(_Symbol, TF, 2), c2 = iClose(_Symbol, TF, 2);
   double h2 = iHigh(_Symbol, TF, 2), l2 = iLow(_Symbol, TF, 2);
   double range = h1 - l1;
   if(range <= 0) return 0;

   double body = MathAbs(c1 - o1);
   double lowerWick = MathMin(o1, c1) - l1;
   double upperWick = h1 - MathMax(o1, c1);
   bool bullReject = c1 > o1 && lowerWick >= MathMax(body, _Point) && c1 >= l1 + 0.60 * range;
   bool bearReject = c1 < o1 && upperWick >= MathMax(body, _Point) && c1 <= h1 - 0.60 * range;
   bool bullEngulf = c1 > o1 && c2 < o2 && c1 >= o2 && o1 <= c2;
   bool bearEngulf = c1 < o1 && c2 > o2 && c1 <= o2 && o1 >= c2;

   double volSum = 0;
   for(int k = 2; k <= 21; k++) volSum += (double)iTickVolume(_Symbol, TF, k);
   if(volSum <= 0) return 0;
   double volAverage = volSum / 20.0;
   if((double)iTickVolume(_Symbol, TF, 1) < ScalpVolMult * volAverage) return 0;

   bool buy = trendFast > trendSlow &&
              (ScalpMinSlopeATR == 0 || (trendFast - trendFastOld) / trendATR >= ScalpMinSlopeATR) &&
              emaFast > emaSlow &&
              l1 <= emaFast + 0.20 * atr && c1 > emaFast && (bullReject || bullEngulf);
   bool sell = trendFast < trendSlow &&
               (ScalpMinSlopeATR == 0 || (trendFastOld - trendFast) / trendATR >= ScalpMinSlopeATR) &&
               emaFast < emaSlow &&
               h1 >= emaFast - 0.20 * atr && c1 < emaFast && (bearReject || bearEngulf);
   if(buy)
   {
      signalStructSL = MathMin(MathMin(l1, l2), iLow(_Symbol, TF, 3)) - 0.15 * atr;
      int resistance = iHighest(_Symbol, TF, MODE_HIGH, 24, 2);
      if(resistance >= 0) signalStructTP = iHigh(_Symbol, TF, resistance);
      return 1;
   }
   if(sell)
   {
      signalStructSL = MathMax(MathMax(h1, h2), iHigh(_Symbol, TF, 3)) + 0.15 * atr;
      int support = iLowest(_Symbol, TF, MODE_LOW, 24, 2);
      if(support >= 0) signalStructTP = iLow(_Symbol, TF, support);
      return -1;
   }
   return 0;
}

// Active variant: retain a closed-bar M15 directional bias and risk guards,
// but recognize both a wider EMA pullback and a confirmed short-range continuation.
int SignalScalpActive()
{
   double atr = Buf(hATR, 1);
   double emaFast = Buf(hCrossFast, 1), emaSlow = Buf(hCrossSlow, 1);
   if(atr == EMPTY_VALUE || atr <= 0 || emaFast == EMPTY_VALUE || emaSlow == EMPTY_VALUE)
      return 0;

   datetime signalTime = iTime(_Symbol, TF, 1);
   int trendShift = iBarShift(_Symbol, PERIOD_M15, signalTime, false) + 1;
   if(trendShift < 1) return 0;
   double trendFast = Buf(hScalpTrendFast, trendShift);
   double trendSlow = Buf(hScalpTrendSlow, trendShift);
   double trendFastOld = Buf(hScalpTrendFast, trendShift + 2);
   double trendATR = Buf(hScalpATR, trendShift);
   double trendADX = Buf(hScalpADX, trendShift, 0);
   if(trendFast == EMPTY_VALUE || trendSlow == EMPTY_VALUE || trendFastOld == EMPTY_VALUE ||
      trendATR == EMPTY_VALUE || trendATR <= 0 || trendADX == EMPTY_VALUE || trendFast == trendSlow)
      return 0;
   if(ActiveMinADX > 0 && trendADX < ActiveMinADX) return 0;
   if(ActiveTrendGapATR > 0 && MathAbs(trendFast - trendSlow) / trendATR < ActiveTrendGapATR)
      return 0;

   int trend = trendFast > trendSlow ? 1 : -1;
   double slope = (trendFast - trendFastOld) / trendATR;
   if(ActiveSlopeATR > 0 && trend * slope < ActiveSlopeATR) return 0;

   double o1 = iOpen(_Symbol, TF, 1), c1 = iClose(_Symbol, TF, 1);
   double h1 = iHigh(_Symbol, TF, 1), l1 = iLow(_Symbol, TF, 1);
   double o2 = iOpen(_Symbol, TF, 2), c2 = iClose(_Symbol, TF, 2);
   double h2 = iHigh(_Symbol, TF, 2), l2 = iLow(_Symbol, TF, 2);
   double range = h1 - l1;
   if(range <= 0) return 0;

   double body = MathAbs(c1 - o1);
   double lowerWick = MathMin(o1, c1) - l1;
   double upperWick = h1 - MathMax(o1, c1);
   bool bullReject = c1 > o1 && lowerWick >= MathMax(body, _Point) && c1 >= l1 + 0.55 * range;
   bool bearReject = c1 < o1 && upperWick >= MathMax(body, _Point) && c1 <= h1 - 0.55 * range;
   bool bullEngulf = c1 > o1 && c2 < o2 && c1 >= o2 && o1 <= c2;
   bool bearEngulf = c1 < o1 && c2 > o2 && c1 <= o2 && o1 >= c2;
   bool bullMomentum = c1 > o1 && body >= 0.35 * range && c1 >= l1 + 0.72 * range;
   bool bearMomentum = c1 < o1 && body >= 0.35 * range && c1 <= h1 - 0.72 * range;

   double volSum = 0;
   for(int k = 2; k <= 21; k++) volSum += (double)iTickVolume(_Symbol, TF, k);
   if(volSum <= 0) return 0;
   double volAverage = volSum / 20.0;
   if((double)iTickVolume(_Symbol, TF, 1) < ActiveVolMult * volAverage) return 0;

   int rangeHighShift = iHighest(_Symbol, TF, MODE_HIGH, ActiveBreakoutBars, 2);
   int rangeLowShift = iLowest(_Symbol, TF, MODE_LOW, ActiveBreakoutBars, 2);
   if(rangeHighShift < 0 || rangeLowShift < 0) return 0;
   double rangeHigh = iHigh(_Symbol, TF, rangeHighShift);
   double rangeLow = iLow(_Symbol, TF, rangeLowShift);

   bool buyPullback = trend > 0 && emaFast > emaSlow &&
      (l1 <= emaFast + ActiveTouchATR * atr || l1 <= emaSlow + ActiveTouchATR * atr) &&
      c1 > emaFast && (bullReject || bullEngulf || bullMomentum);
   bool sellPullback = trend < 0 && emaFast < emaSlow &&
      (h1 >= emaFast - ActiveTouchATR * atr || h1 >= emaSlow - ActiveTouchATR * atr) &&
      c1 < emaFast && (bearReject || bearEngulf || bearMomentum);
   bool buyContinuation = trend > 0 && emaFast > emaSlow && c1 > rangeHigh && bullMomentum;
   bool sellContinuation = trend < 0 && emaFast < emaSlow && c1 < rangeLow && bearMomentum;

   if(buyPullback || buyContinuation)
   {
      signalStructSL = MathMin(MathMin(l1, l2), iLow(_Symbol, TF, 3)) - 0.15 * atr;
      int resistance = iHighest(_Symbol, TF, MODE_HIGH, 24, 2);
      if(resistance >= 0)
      {
         double level = iHigh(_Symbol, TF, resistance);
         if(level > c1) signalStructTP = level;
      }
      return 1;
   }
   if(sellPullback || sellContinuation)
   {
      signalStructSL = MathMax(MathMax(h1, h2), iHigh(_Symbol, TF, 3)) + 0.15 * atr;
      int support = iLowest(_Symbol, TF, MODE_LOW, 24, 2);
      if(support >= 0)
      {
         double level = iLow(_Symbol, TF, support);
         if(level < c1) signalStructTP = level;
      }
      return -1;
   }
   return 0;
}

int SignalAutoAdaptive()
{
   // 1) สภาวะตลาดเปิดรอบลอนดอน/นิวยอร์ก: ตรวจสอบ Session Breakout ก่อนเป็นอันดับแรก
   int sigSession = SignalSessionBreakout();
   if(sigSession != 0)
   {
      PrintFormat("Adaptive Mode: ตรวจพบจังหวะเปิดตลาด -> เลือกใช้ [SESSION_BREAKOUT] ทิศทาง %s",
                  sigSession > 0 ? "BUY" : "SELL");
      return sigSession;
   }

   // 2) ตรวจสอบความแรงของแนวโน้มตลาดด้วย ADX
   double adxVal = Buf(hADX, 1, 0);
   if(adxVal == EMPTY_VALUE) return 0;

   // สภาวะเทรนด์ชัดเจนและแข็งแกร่ง (ADX >= 25) -> รอจังหวะย่อในทิศทางเทรนด์ใหญ่
   if(adxVal >= 25.0)
   {
      int sigTrend = SignalTrendPullback();
      if(sigTrend != 0)
      {
         PrintFormat("Adaptive Mode: ตลาดมีเทรนด์ชัดเจน (ADX=%.1f) -> เลือกใช้ [TREND_PULLBACK] ทิศทาง %s",
                     adxVal, sigTrend > 0 ? "BUY" : "SELL");
         return sigTrend;
      }
   }
   // สภาวะตลาดเริ่มมีโมเมนตัม (ADX >= ADX_Min) -> มองหาเบรกเอาท์กรอบราคา
   else if(adxVal >= ADX_Min)
   {
      int sigDonchian = SignalDonchian();
      if(sigDonchian != 0)
      {
         PrintFormat("Adaptive Mode: ตลาดเริ่มมีโมเมนตัม (ADX=%.1f) -> เลือกใช้ [DONCHIAN_BREAKOUT] ทิศทาง %s",
                     adxVal, sigDonchian > 0 ? "BUY" : "SELL");
         return sigDonchian;
      }
   }
   // สภาวะไซด์เวย์ไร้ทิศทาง (ADX < 20) -> งดเข้าเทรดเพื่อรักษาเงินทุนพอร์ตเล็ก
   else
   {
      return 0;
   }

   return 0;
}

int GetSignal()
{
   switch(Strategy)
   {
      case STRAT_AUTO_ADAPTIVE:    return SignalAutoAdaptive();
      case STRAT_TREND_PULLBACK:   return SignalTrendPullback();
      case STRAT_DONCHIAN:         return SignalDonchian();
      case STRAT_SESSION_BREAKOUT: return SignalSessionBreakout();
      case STRAT_EMA_CROSS:        return SignalEmaCross();
      case STRAT_ALL_DAY_BOS:      return SignalAllDayBOS();
      case STRAT_DAYTRADE_COMBO:   return SignalDayTradeCombo();
      case STRAT_SCALP_PA:         return SignalScalpPA();
      case STRAT_SCALP_ACTIVE:     return SignalScalpActive();
   }
   return 0;
}

//+------------------------------------------------------------------+
//| คำนวณ lot จาก % ความเสี่ยงและระยะ SL                               |
//| พอร์ตเล็ก: ถ้า lot ต่ำสุดยังเสี่ยงเกินเพดาน -> คืน 0 (ข้ามไม้)           |
//+------------------------------------------------------------------+
double CalcLot(double slDistance, int dir, double entryPrice, double lotMultiplier)
{
   double balance   = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance <= 0 || slDistance <= 0 || entryPrice <= 0) return 0;
   ENUM_ORDER_TYPE orderType = (dir > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double estimatedProfit = 0;
   double stopPrice = entryPrice - dir * slDistance;
   if(!OrderCalcProfit(orderType, _Symbol, 1.0, entryPrice, stopPrice, estimatedProfit))
   {
      PrintFormat("ข้ามไม้: คำนวณผลขาดทุนที่ SL ไม่สำเร็จ error=%d", GetLastError());
      return 0;
   }
   if(estimatedProfit >= 0)
   {
      Print("ข้ามไม้: ราคา SL ไม่ได้คำนวณเป็นผลขาดทุน");
      return 0;
   }
   double lossPerLot = MathAbs(estimatedProfit);                 // account currency at 1.00 lot
   if(lossPerLot <= 0) return 0;
   // Equity scaling: $100 -> 0.01 lot, $200 -> 0.02 lot, etc.
   // The estimated stop loss remains subject to the hard MaxRiskPercent guard below.
   double lot = (balance / 100.0) * LotPer100USD * MathMax(1.0, lotMultiplier);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0 || vmin <= 0 || vmax < vmin) return 0;

   lot = NormalizeDouble(MathFloor(lot / step) * step, 8);
   if(lot < vmin) lot = vmin;                                   // lot ต่ำสุดของโบรกเกอร์
   lot = MathMin(lot, vmax);

   double realRiskPct = lot * lossPerLot / balance * 100.0;     // ความเสี่ยงจริงที่ lot นี้
   if(realRiskPct > MaxRiskPercent)
   {
      PrintFormat("ข้ามไม้: SL %.2f$ ที่ lot %.2f เสี่ยงจริง %.1f%% เกินเพดาน %.1f%%",
                  slDistance, lot, realRiskPct, MaxRiskPercent);
      return 0;
   }

   // ตรวจ margin ว่าไม่กินเกินสัดส่วนที่ตั้งไว้
   double margin = 0;
   double marginPrice = (dir > 0) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                  : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   if(!OrderCalcMargin(orderType, _Symbol, lot, marginPrice, margin))
   {
      PrintFormat("ข้ามไม้: คำนวณ margin ไม่สำเร็จ error=%d", GetLastError());
      return 0;
   }
   else
   {
      if(margin > AccountInfoDouble(ACCOUNT_MARGIN_FREE) * MaxMarginUsePct / 100.0)
      {
         PrintFormat("ข้ามไม้: margin %.2f เกิน %.0f%% ของ free margin", margin, MaxMarginUsePct);
         return 0;
      }
   }
   return lot;
}

//+------------------------------------------------------------------+
void OpenTrade(int dir)
{
   double atr = Buf(hATR, 1);
   if(atr == EMPTY_VALUE || atr <= 0) return;
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double entry = (dir > 0) ? ask : bid;
   double slDist = (signalStructSL > 0)
                   ? dir * (entry - signalStructSL)
                   : atr * SL_ATR_Mult;
   if(slDist <= 0) { Print("ข้ามไม้: SL โครงสร้างอยู่ผิดฝั่ง"); return; }

   // ขยาย SL ที่แคบเกินไปโดยคงทิศทางออกจาก entry; SL กว้างเกินให้ข้าม
   slDist = MathMax(slDist, MinRiskATR * atr);
   double minDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   slDist = MathMax(slDist, minDist);
   bool scalpMode = (Strategy == STRAT_SCALP_PA || Strategy == STRAT_SCALP_ACTIVE);
   if(scalpMode && slDist / _Point > ScalpMaxSLPoints)
   {
      PrintFormat("ข้าม scalp: SL %.0f points เกินเพดาน %d points", slDist / _Point, ScalpMaxSLPoints);
      return;
   }
   if(slDist > MaxRiskATR * atr || (MaxSL_USD > 0 && slDist > MaxSL_USD))
   {
      PrintFormat("ข้ามไม้: structural SL กว้าง %.2f (ATR %.2f, limit %.1fxATR)",
                  slDist, atr, MaxRiskATR);
      return;
   }

   double sl = entry - dir * slDist;
   double targetDist = slDist * RR;
   if(scalpMode)
   {
      double structuralTargetDist = dir * (signalStructTP - entry);
      if(structuralTargetDist < slDist * ScalpMinRR)
      {
         if(Strategy == STRAT_SCALP_ACTIVE && signalStructTP <= 0)
            targetDist = slDist * ScalpMinRR; // no forward structure: use the configured minimum-R target
         else
         {
            PrintFormat("ข้าม scalp: แนวรับ/ต้านใกล้เกินไปสำหรับเป้าหมายขั้นต่ำ %.2fR", ScalpMinRR);
            return;
         }
      }
      else
         targetDist = MathMin(structuralTargetDist, slDist * ScalpMaxRR);
   }
   double tp = entry + dir * targetDist;
   datetime lastClose;
   int lossStreak = ConsecLosses(lastClose);
   int recoveryLevel = EnableRecoverySizing
                       ? (int)MathMin((double)lossStreak, (double)MathMax(0, RecoveryMaxSteps))
                       : 0;
   double lotMultiplier = MathPow(MathMax(1.0, RecoveryMultiplier), recoveryLevel);
   double lot = CalcLot(slDist, dir, entry, lotMultiplier);
   if(lot <= 0) return;

   bool ok = false;

   if(dir > 0)
      ok = trade.Buy(lot, _Symbol, ask,
                     NormalizeDouble(sl, _Digits),
                     NormalizeDouble(tp, _Digits), "XAU_PRO");
   else
      ok = trade.Sell(lot, _Symbol, bid,
                      NormalizeDouble(sl, _Digits),
                      NormalizeDouble(tp, _Digits), "XAU_PRO");

   uint rc = trade.ResultRetcode();
   bool executed = ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_DONE_PARTIAL) &&
                   trade.ResultDeal() > 0;
   if(executed)
   {
      MqlDateTime t; TimeToStruct(TimeCurrent(), t);
      lastTradeDay = t.year * 1000 + t.day_of_year;
   }
   else
      PrintFormat("order ยังไม่ถูก execute: request=%s retcode=%u deal=%I64u %s",
                  ok ? "accepted" : "rejected", rc, trade.ResultDeal(),
                  trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
void OnTick()
{
   ManageBreakEven();                 // เช็คทุก tick เพราะกำไรอาจถึงเกณฑ์กลางแท่ง

   // ที่เหลือทำงานครั้งเดียวต่อแท่ง (ตอนแท่งใหม่เปิด) = ใช้แท่งที่ปิดแล้วเท่านั้น
   datetime bt = iTime(_Symbol, TF, 0);
   if(bt == lastBarTime) return;
   lastBarTime = bt;

   ManageTimeExit();
   if(HasPosition()) return;          // เปิดทีละ 1 ไม้
   if(!FiltersOK())  return;

   signalStructSL = 0;
   signalStructTP = 0;
   int sig = GetSignal();
   if(sig != 0) OpenTrade(sig);
}
//+------------------------------------------------------------------+
