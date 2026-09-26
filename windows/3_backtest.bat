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
echo Backtesting all strategies (walk-forward) and simulating FTMO challenges...
set STRATS=trend_breakout rsi2_reversion london_breakout ny_breakout
python -m trading_ai backtest --strategy %STRATS% --walk-forward > reports\3_backtest.txt 2>&1
echo. >> reports\3_backtest.txt
python -m trading_ai challenge --strategy %STRATS% --walk-forward >> reports\3_backtest.txt 2>&1
type reports\3_backtest.txt
echo.
echo Saved to reports\3_backtest.txt  - send this file to Claude.
pause
