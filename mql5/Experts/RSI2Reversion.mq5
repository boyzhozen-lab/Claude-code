//+------------------------------------------------------------------+
//| RSI2Reversion.mq5                                                |
//| Strategy B: RSI(2) mean reversion on index CFDs, daily bars,     |
//| long only. Mirrors python/trading_ai/strategies/rsi2_reversion.py|
//| and the backtest engine:                                         |
//|  - signals are read on the last CLOSED daily bar and acted on    |
//|    right after the next daily bar opens                          |
//|  - entry:  close > SMA(trend) and RSI(2) < entry level           |
//|  - exit:   close > SMA(exit), or held for InpMaxBars days        |
//|  - stop:   InpStopAtr x ATR, placed on the server at entry       |
//|  - size:   InpRiskPct % of balance lost if the stop is hit       |
//| Attach to ONE chart; it trades every symbol in InpSymbols.       |
//| Run RiskGuard on another chart alongside it.                     |
//+------------------------------------------------------------------+
#property copyright "Trading AI"
#property version   "1.00"
#property description "RSI(2) mean reversion on indices (D1, long only). Use together with RiskGuard."

#include <Trade/Trade.mqh>

input string InpSymbols          = "US500m,USTECm,US30m"; // Symbols, comma separated
input double InpRiskPct          = 0.5;   // Risk per trade, % of balance
input int    InpRsiLen           = 2;     // RSI length
input double InpEntryRsi         = 10.0;  // Buy when RSI is below this
input int    InpTrendLen         = 200;   // Only buy when close is above this SMA
input int    InpExitLen          = 5;     // Exit when close is above this SMA
input int    InpAtrLen           = 10;    // ATR length for the stop
input double InpStopAtr          = 3.0;   // Stop distance in ATRs
input int    InpMaxBars          = 10;    // Time exit after this many days
input int    InpEntryWindowHours = 6;     // Only open new trades this long after the daily bar opens
input long   InpMagic            = 2201;  // Magic number (journal maps it to rsi2_reversion)

struct SymbolState
  {
   string   name;
   datetime handled;   // daily bar already processed
   int      h_rsi;
   int      h_trend;
   int      h_exit;
   int      h_atr;
   string   last_note;
  };

SymbolState g_syms[];
CTrade      g_trade;

//--- helpers --------------------------------------------------------
double Value(const int handle, const int shift)
  {
   double v[1];
   if(handle == INVALID_HANDLE || CopyBuffer(handle, 0, shift, 1, v) != 1)
      return EMPTY_VALUE;
   return v[0];
  }

ulong FindPosition(const string symbol)
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return ticket;
     }
   return 0;
  }

int VolumeDigits(const double step)
  {
   int d = 0;
   double s = step;
   while(d < 8 && MathAbs(s - MathRound(s)) > 1e-9)
     {
      s *= 10;
      d++;
     }
   return d;
  }

// Returns true when the bar can be marked as handled (opened, or skipped for a lasting reason).
bool OpenLong(SymbolState &s, const double stop_dist)
  {
   double ask = SymbolInfoDouble(s.name, SYMBOL_ASK);
   int digits = (int)SymbolInfoInteger(s.name, SYMBOL_DIGITS);
   if(ask <= 0)
      return false;
   double sl = NormalizeDouble(ask - stop_dist, digits);

   double pnl_one_lot = 0;
   if(!OrderCalcProfit(ORDER_TYPE_BUY, s.name, 1.0, ask, sl, pnl_one_lot) || pnl_one_lot >= 0)
      return false;
   double risk_money = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0;
   double step = SymbolInfoDouble(s.name, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(s.name, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(s.name, SYMBOL_VOLUME_MAX);
   double lots = MathFloor(risk_money / -pnl_one_lot / step) * step;
   if(lots < vmin)
     {
      s.last_note = StringFormat("skipped: %.2f%% risk is below the minimum lot", InpRiskPct);
      PrintFormat("RSI2 %s: %s", s.name, s.last_note);
      return true;
     }
   lots = NormalizeDouble(MathMin(lots, vmax), VolumeDigits(step));

   if(!g_trade.Buy(lots, s.name, 0, sl, 0, "rsi2_reversion"))
     {
      PrintFormat("RSI2 %s: buy failed %d %s", s.name, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      return false;
     }
   s.last_note = StringFormat("bought %.2f lots, stop %s", lots, DoubleToString(sl, digits));
   PrintFormat("RSI2 %s: %s", s.name, s.last_note);
   return true;
  }

//--- core logic, once per new daily bar per symbol -----------------
void Process(SymbolState &s)
  {
   datetime bar = iTime(s.name, PERIOD_D1, 0);
   if(bar == 0 || bar == s.handled)
      return;

   double close1 = iClose(s.name, PERIOD_D1, 1);
   double rsi1   = Value(s.h_rsi, 1);
   double trend1 = Value(s.h_trend, 1);
   double exit1  = Value(s.h_exit, 1);
   double atr1   = Value(s.h_atr, 1);
   if(close1 <= 0 || rsi1 == EMPTY_VALUE || trend1 == EMPTY_VALUE || exit1 == EMPTY_VALUE || atr1 == EMPTY_VALUE || atr1 <= 0)
      return;   // history not loaded yet: retry on the next timer

   bool done = true;

   // 1. Exit decided at the previous close.
   ulong ticket = FindPosition(s.name);
   if(ticket > 0 && PositionSelectByTicket(ticket))
     {
      int held = iBarShift(s.name, PERIOD_D1, (datetime)PositionGetInteger(POSITION_TIME));
      string reason = close1 > exit1 ? "signal" : (held >= InpMaxBars ? "time" : "");
      if(reason != "")
        {
         if(g_trade.PositionClose(ticket))
           {
            s.last_note = "closed (" + reason + ")";
            PrintFormat("RSI2 %s: %s after %d days", s.name, s.last_note, held);
            ticket = 0;
           }
         else
            done = false;
        }
     }

   // 2. Entry decided at the previous close.
   bool signal = close1 > trend1 && rsi1 < InpEntryRsi;
   if(ticket == 0 && signal)
     {
      if(TimeCurrent() - bar <= InpEntryWindowHours * 3600)
         done = OpenLong(s, InpStopAtr * atr1) && done;
      else
         s.last_note = "signal missed: too late in the day";
     }

   if(done)
      s.handled = bar;
  }

void ShowPanel()
  {
   string text = StringFormat("RSI2Reversion  risk %.2f%%  entry RSI<%.0f  magic %I64d\n", InpRiskPct, InpEntryRsi, InpMagic);
   for(int i = 0; i < ArraySize(g_syms); i++)
     {
      double rsi1 = Value(g_syms[i].h_rsi, 1);
      text += StringFormat("%-10s RSI(2)=%5.1f  %s  %s\n", g_syms[i].name, rsi1 == EMPTY_VALUE ? 0.0 : rsi1,
                           FindPosition(g_syms[i].name) > 0 ? "[IN TRADE]" : "", g_syms[i].last_note);
     }
   Comment(text);
  }

//--- events ---------------------------------------------------------
int OnInit()
  {
   string parts[];
   int n = StringSplit(InpSymbols, ',', parts);
   ArrayResize(g_syms, 0);
   for(int i = 0; i < n; i++)
     {
      string name = parts[i];
      StringTrimLeft(name);
      StringTrimRight(name);
      if(name == "")
         continue;
      if(!SymbolSelect(name, true))
        {
         PrintFormat("RSI2: symbol %s not found", name);
         return INIT_PARAMETERS_INCORRECT;
        }
      SymbolState s;
      s.name      = name;
      s.handled   = 0;
      s.last_note = "";
      s.h_rsi     = iRSI(name, PERIOD_D1, InpRsiLen, PRICE_CLOSE);
      s.h_trend   = iMA(name, PERIOD_D1, InpTrendLen, 0, MODE_SMA, PRICE_CLOSE);
      s.h_exit    = iMA(name, PERIOD_D1, InpExitLen, 0, MODE_SMA, PRICE_CLOSE);
      s.h_atr     = iATR(name, PERIOD_D1, InpAtrLen);
      if(s.h_rsi == INVALID_HANDLE || s.h_trend == INVALID_HANDLE || s.h_exit == INVALID_HANDLE || s.h_atr == INVALID_HANDLE)
        {
         PrintFormat("RSI2: could not create indicators for %s", name);
         return INIT_FAILED;
        }
      int k = ArraySize(g_syms);
      ArrayResize(g_syms, k + 1);
      g_syms[k] = s;
     }
   if(ArraySize(g_syms) == 0)
      return INIT_PARAMETERS_INCORRECT;

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(100);
   EventSetTimer(10);
   PrintFormat("RSI2Reversion started on %d symbol(s), risk %.2f%% per trade", ArraySize(g_syms), InpRiskPct);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   for(int i = 0; i < ArraySize(g_syms); i++)
     {
      IndicatorRelease(g_syms[i].h_rsi);
      IndicatorRelease(g_syms[i].h_trend);
      IndicatorRelease(g_syms[i].h_exit);
      IndicatorRelease(g_syms[i].h_atr);
     }
   Comment("");
  }

void OnTimer()
  {
   for(int i = 0; i < ArraySize(g_syms); i++)
      Process(g_syms[i]);
   ShowPanel();
  }

void OnTick() { }
//+------------------------------------------------------------------+
