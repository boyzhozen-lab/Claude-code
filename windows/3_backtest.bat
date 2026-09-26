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
echo Backtesting (walk-forward) and simulating FTMO challenges...
set STRATS=trend_breakout rsi2_reversion london_breakout ny_breakout
set OUT=reports\3_backtest.txt
echo ===== A. ALL STRATEGIES ===== > %OUT%
python -m trading_ai backtest --strategy %STRATS% --walk-forward >> %OUT% 2>&1
echo. >> %OUT%
echo ===== B. RSI2 REVERSION ONLY (indices) ===== >> %OUT%
python -m trading_ai challenge --strategy rsi2_reversion --walk-forward --risks 0.5 0.75 1.0 1.5 2.0 >> %OUT% 2>&1
echo. >> %OUT%
echo ===== C. TREND BREAKOUT ON GOLD (long history) ===== >> %OUT%
python -m trading_ai backtest --strategy trend_breakout --symbols GOLD --walk-forward >> %OUT% 2>&1
type %OUT%
echo.
echo Saved to %OUT%  - send this file to Claude.
pause
