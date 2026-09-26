//+------------------------------------------------------------------+
//| RiskGuard.mq5                                                    |
//| Account-level risk limits for prop-firm rules.                   |
//|                                                                  |
//| Attach to ONE chart. It watches every position on the account    |
//| (manual or EA) and:                                              |
//|  - closes everything and blocks trading for the rest of the day  |
//|    when the daily loss limit is reached                          |
//|  - closes everything and blocks trading permanently when the     |
//|    maximum total loss is reached                                 |
//|  - closes positions that still have no stop loss after a grace   |
//|    period                                                        |
//|  - closes the newest position when combined open risk is too big |
//|  - obeys a kill switch file: MQL5\Files\trading_ai\kill_switch   |
//|  - writes MQL5\Files\trading_ai\heartbeat.json for monitoring    |
//| It never opens trades.                                           |
//+------------------------------------------------------------------+
#property copyright "Trading AI"
#property version   "1.00"
#property description "Account-level risk limits: daily loss, max loss, mandatory stop loss, open risk, kill switch."

#include <Trade/Trade.mqh>

input double InpInitialBalance = 0;     // Initial balance (0 = balance when first attached)
input double InpDailyLossPct   = 3.0;   // Daily loss limit, % of initial balance (FTMO: 5)
input double InpMaxLossPct     = 7.0;   // Max total loss, % of initial balance (FTMO: 10)
input double InpMaxOpenRiskPct = 1.5;   // Max combined risk to stop loss of open positions, %
input bool   InpRequireSL      = true;  // Close positions that have no stop loss
input int    InpNoSLGraceSec   = 60;    // Seconds allowed to add a stop loss
input bool   InpPushNotify     = true;  // Also send push notifications to MT5 mobile
input bool   InpResetTotalLock = false; // Set true once to clear a max-loss lock

enum GuardState { STATE_OK, STATE_DAILY_LOCK, STATE_TOTAL_LOCK, STATE_KILL };

const string FILES_DIR   = "trading_ai";
const string KILL_FILE   = "trading_ai\\kill_switch";
const string HEART_FILE  = "trading_ai\\heartbeat.json";

CTrade   g_trade;
string   g_prefix;
datetime g_last_heartbeat = 0;
string   g_last_notice = "";
datetime g_last_notice_time = 0;

//--- persistent values (survive terminal restarts) -----------------
double GV(const string key, const double def)
  {
   string name = g_prefix + key;
   return GlobalVariableCheck(name) ? GlobalVariableGet(name) : def;
  }

void SetGV(const string key, const double value)
  {
   GlobalVariableSet(g_prefix + key, value);
  }

long DayNumber()
  {
   return (long)(TimeTradeServer() / 86400);   // broker server calendar day
  }

//--- messages -------------------------------------------------------
void Notify(const string msg)
  {
   // Same message at most once per 10 minutes.
   if(msg == g_last_notice && TimeCurrent() - g_last_notice_time < 600)
      return;
   g_last_notice = msg;
   g_last_notice_time = TimeCurrent();
   string text = "RiskGuard " + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + ": " + msg;
   Print(text);
   Alert(text);
   if(InpPushNotify && TerminalInfoInteger(TERMINAL_NOTIFICATIONS_ENABLED))
      SendNotification(text);
  }

//--- state ----------------------------------------------------------
void RollDay()
  {
   double today = (double)DayNumber();
   if(GV("day", -1) != today)
     {
      SetGV("day", today);
      SetGV("daystart", AccountInfoDouble(ACCOUNT_BALANCE));
      PrintFormat("RiskGuard: new trading day, start balance %.2f", AccountInfoDouble(ACCOUNT_BALANCE));
     }
  }

GuardState State()
  {
   if(FileIsExist(KILL_FILE))
      return STATE_KILL;
   if(GV("totallock", 0) > 0)
      return STATE_TOTAL_LOCK;
   if(GV("daylock", -1) == (double)DayNumber())
      return STATE_DAILY_LOCK;
   return STATE_OK;
  }

string StateName(const GuardState s)
  {
   switch(s)
     {
      case STATE_DAILY_LOCK: return "DAILY LIMIT - blocked until tomorrow";
      case STATE_TOTAL_LOCK: return "MAX LOSS - blocked (reset manually)";
      case STATE_KILL:       return "KILL SWITCH - blocked";
     }
   return "OK";
  }

//--- actions --------------------------------------------------------
void FlattenAll()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && !g_trade.PositionClose(ticket))
         PrintFormat("RiskGuard: close %I64u failed: %d %s", ticket, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
     }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0 && !g_trade.OrderDelete(ticket))
         PrintFormat("RiskGuard: delete order %I64u failed: %d", ticket, g_trade.ResultRetcode());
     }
  }

void EnforceStopLoss()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || PositionGetDouble(POSITION_SL) != 0)
         continue;
      long age = (long)(TimeCurrent() - (datetime)PositionGetInteger(POSITION_TIME));
      if(age < InpNoSLGraceSec)
         continue;
      string symbol = PositionGetString(POSITION_SYMBOL);
      if(g_trade.PositionClose(ticket))
         Notify(StringFormat("closed %s #%I64u: no stop loss after %d s", symbol, ticket, InpNoSLGraceSec));
     }
  }

// Money lost if the position's stop loss is hit (0 if the stop is in profit or missing).
double RiskToStop(const ulong ticket)
  {
   if(!PositionSelectByTicket(ticket))
      return 0;
   double sl = PositionGetDouble(POSITION_SL);
   if(sl == 0)
      return 0;
   ENUM_ORDER_TYPE type = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double profit = 0;
   if(!OrderCalcProfit(type, PositionGetString(POSITION_SYMBOL), PositionGetDouble(POSITION_VOLUME),
                       PositionGetDouble(POSITION_PRICE_OPEN), sl, profit))
      return 0;
   return profit < 0 ? -profit : 0;
  }

double OpenRisk(ulong &newest)
  {
   double total = 0;
   long newest_time = 0;
   newest = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      long opened = PositionGetInteger(POSITION_TIME_MSC);
      total += RiskToStop(ticket);
      if(opened > newest_time)
        {
         newest_time = opened;
         newest = ticket;
        }
     }
   return total;
  }

void WriteHeartbeat(const GuardState s, const double init, const double day_start, const double daily_pnl, const double open_risk)
  {
   int h = FileOpen(HEART_FILE, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, StringFormat(
      "{\"time\": \"%s\", \"login\": %I64d, \"state\": \"%s\", \"balance\": %.2f, \"equity\": %.2f, "
      "\"initial_balance\": %.2f, \"day_start_balance\": %.2f, \"daily_pnl\": %.2f, "
      "\"daily_limit_pct\": %.2f, \"max_loss_pct\": %.2f, \"open_risk\": %.2f, \"positions\": %d}",
      TimeToString(TimeTradeServer(), TIME_DATE | TIME_SECONDS), AccountInfoInteger(ACCOUNT_LOGIN),
      EnumToString(s), AccountInfoDouble(ACCOUNT_BALANCE), AccountInfoDouble(ACCOUNT_EQUITY),
      init, day_start, daily_pnl, InpDailyLossPct, InpMaxLossPct, open_risk, PositionsTotal()));
   FileClose(h);
  }

//--- main check -----------------------------------------------------
void Check()
  {
   RollDay();
   double init      = GV("init", AccountInfoDouble(ACCOUNT_BALANCE));
   double equity    = AccountInfoDouble(ACCOUNT_EQUITY);
   double day_start = GV("daystart", AccountInfoDouble(ACCOUNT_BALANCE));
   double daily_pnl = equity - day_start;
   double floor_eq  = init * (1.0 - InpMaxLossPct / 100.0);

   if(State() == STATE_OK)
     {
      if(equity <= floor_eq)
        {
         SetGV("totallock", 1);
         Notify(StringFormat("MAX LOSS reached (equity %.2f <= %.2f). Closing everything, trading blocked.", equity, floor_eq));
        }
      else if(daily_pnl <= -init * InpDailyLossPct / 100.0)
        {
         SetGV("daylock", (double)DayNumber());
         Notify(StringFormat("DAILY LIMIT reached (%.2f today). Closing everything until tomorrow.", daily_pnl));
        }
     }

   GuardState s = State();
   double open_risk = 0;
   if(s != STATE_OK)
     {
      if(PositionsTotal() > 0 || OrdersTotal() > 0)
        {
         if(s == STATE_KILL)
            Notify("kill switch file found: closing everything.");
         FlattenAll();
        }
     }
   else
     {
      if(InpRequireSL)
         EnforceStopLoss();
      ulong newest = 0;
      open_risk = OpenRisk(newest);
      double max_risk = init * InpMaxOpenRiskPct / 100.0;
      if(open_risk > max_risk && newest > 0 && PositionSelectByTicket(newest))
        {
         string symbol = PositionGetString(POSITION_SYMBOL);
         if(g_trade.PositionClose(newest))
            Notify(StringFormat("closed newest position %s #%I64u: open risk %.2f > limit %.2f", symbol, newest, open_risk, max_risk));
        }
     }

   if(TimeCurrent() - g_last_heartbeat >= 15)
     {
      WriteHeartbeat(s, init, day_start, daily_pnl, open_risk);
      g_last_heartbeat = TimeCurrent();
     }

   Comment(StringFormat(
      "RiskGuard  [%s]\n"
      "Today P&L: %.2f  (%.2f%%)   limit -%.1f%%\n"
      "Equity: %.2f   floor: %.2f  (-%.1f%%)\n"
      "Open risk to stops: %.2f%%   limit %.1f%%",
      StateName(s), daily_pnl, 100.0 * daily_pnl / init, InpDailyLossPct,
      equity, floor_eq, InpMaxLossPct, 100.0 * open_risk / init, InpMaxOpenRiskPct));
  }

//--- events ---------------------------------------------------------
int OnInit()
  {
   g_prefix = "RG_" + IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN)) + "_";
   if(InpResetTotalLock)
     {
      SetGV("totallock", 0);
      Print("RiskGuard: max-loss lock cleared by input");
     }
   if(InpInitialBalance > 0)
      SetGV("init", InpInitialBalance);
   else if(GV("init", 0) <= 0)
      SetGV("init", AccountInfoDouble(ACCOUNT_BALANCE));

   FolderCreate(FILES_DIR);
   g_trade.SetDeviationInPoints(50);
   g_trade.SetAsyncMode(false);
   EventSetTimer(1);
   PrintFormat("RiskGuard started: initial %.2f, daily -%.1f%%, max -%.1f%%, open risk %.1f%%",
               GV("init", 0), InpDailyLossPct, InpMaxLossPct, InpMaxOpenRiskPct);
   Check();
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Comment("");
  }

void OnTimer()  { Check(); }
void OnTick()   { Check(); }

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
  {
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
      Check();
  }
//+------------------------------------------------------------------+
