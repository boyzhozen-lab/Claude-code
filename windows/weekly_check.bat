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
set OUT=reports\weekly_check.txt
echo ===== FORWARD CHECK: live EA vs backtest ===== > %OUT%
python -m trading_ai forward-check --strategy rsi2_reversion --since 2026-09-28 >> %OUT% 2>&1
echo. >> %OUT%
echo ===== JOURNAL ===== >> %OUT%
python -m trading_ai stats --by strategy_id symbol exit_reason >> %OUT% 2>&1
type %OUT%
echo.
echo Saved to %OUT%  - send this file to Claude every weekend.
pause
