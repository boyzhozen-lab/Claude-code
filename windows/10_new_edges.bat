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
set OUT=reports\10_new_edges.txt
echo ===== A. TURN OF MONTH (US indices, walk-forward) ===== > %OUT%
python -m trading_ai backtest --strategy turn_of_month --walk-forward >> %OUT% 2>&1
echo. >> %OUT%
echo ===== B. RSI2 BOTH WAYS (Gold + Forex, walk-forward) ===== >> %OUT%
python -m trading_ai backtest --strategy rsi2_both --walk-forward >> %OUT% 2>&1
echo. >> %OUT%
echo ===== C. COMBINED: RSI2 + TURN OF MONTH + RSI2 BOTH (correlation) ===== >> %OUT%
python -m trading_ai backtest --strategy rsi2_reversion turn_of_month rsi2_both --walk-forward >> %OUT% 2>&1
echo. >> %OUT%
echo ===== D. CHALLENGE: RSI2 + TURN OF MONTH ===== >> %OUT%
python -m trading_ai challenge --strategy rsi2_reversion turn_of_month --walk-forward --risks 0.5 0.75 1.0 1.25 1.5 >> %OUT% 2>&1
type %OUT%
echo.
echo Saved to %OUT%  - send this file to Claude.
pause
