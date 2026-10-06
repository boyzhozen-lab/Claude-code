@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
if not exist .venv\Scripts\activate.bat (
  echo [ERROR] Not installed yet. Run windows\0_setup.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
if not exist reports mkdir reports
set OUT=reports\14_scalping_lab.txt
set SYM=GOLD NAS100 SPX500 EURUSD
echo Downloading 5 years of M1/M5 bars (several minutes, only the first time)...
python -m trading_ai fetch-bars --symbols %SYM% --timeframes M1 --years 1 > %OUT% 2>&1
python -m trading_ai fetch-bars --symbols %SYM% --timeframes M5 --years 5 >> %OUT% 2>&1
echo. >> %OUT%
echo ===== 1. COST vs TYPICAL BAR, per timeframe ===== >> %OUT%
python -m trading_ai cost-check --symbols %SYM% >> %OUT% 2>&1
echo. >> %OUT%
echo ===== 2. M5 SCALP: MEAN REVERSION (RSI2 both ways, walk-forward) ===== >> %OUT%
python -m trading_ai backtest --strategy rsi2_both --timeframe M5 --symbols %SYM% --walk-forward >> %OUT% 2>&1
echo. >> %OUT%
echo ===== 3. M5 SCALP: BREAKOUT MOMENTUM (walk-forward) ===== >> %OUT%
python -m trading_ai backtest --strategy trend_breakout --timeframe M5 --symbols %SYM% --walk-forward >> %OUT% 2>&1
type %OUT%
echo.
echo Saved to %OUT%  - send this file to Claude.
pause
