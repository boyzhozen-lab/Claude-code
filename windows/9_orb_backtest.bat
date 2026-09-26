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
set OUT=reports\9_orb_backtest.txt
echo Downloading 5 years of M5 bars for NAS100 (a few minutes)...
python -m trading_ai fetch-bars --symbols NAS100 --timeframes M5 D1 > %OUT% 2>&1
echo. >> %OUT%
python -m trading_ai backtest-orb --symbol NAS100 --compare >> %OUT% 2>&1
type %OUT%
echo.
echo Saved to %OUT%  - send this file to Claude.
pause
