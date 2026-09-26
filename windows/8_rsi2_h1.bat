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
set OUT=reports\8_rsi2_h1.txt
echo ===== RSI2 on H1 bars, US indices (walk-forward) ===== > %OUT%
python -m trading_ai backtest --strategy rsi2_reversion --timeframe H1 --symbols SPX500 NAS100 DOW30 --walk-forward >> %OUT% 2>&1
echo. >> %OUT%
echo ===== Challenge: RSI2 H1 on US indices ===== >> %OUT%
python -m trading_ai challenge --strategy rsi2_reversion --timeframe H1 --symbols SPX500 NAS100 DOW30 --walk-forward --risks 0.25 0.5 0.75 1.0 >> %OUT% 2>&1
type %OUT%
echo.
echo Saved to %OUT%  - send this file to Claude.
pause
