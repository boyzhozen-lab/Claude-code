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
set IDX=GER40 UK100 JP225 AUS200 FRA40 EU50 HK50
set OUT=reports\7_rsi2_indices.txt
echo Downloading daily data for more indices...
python -m trading_ai fetch-bars --symbols %IDX% --timeframes D1 > %OUT% 2>&1
echo. >> %OUT%
echo ===== RSI2 on every index (walk-forward) ===== >> %OUT%
python -m trading_ai backtest --strategy rsi2_reversion --walk-forward >> %OUT% 2>&1
echo. >> %OUT%
echo ===== Challenge simulation, RSI2 on every index ===== >> %OUT%
python -m trading_ai challenge --strategy rsi2_reversion --walk-forward --risks 0.5 0.75 1.0 1.25 1.5 >> %OUT% 2>&1
type %OUT%
echo.
echo Saved to %OUT%  - send this file to Claude.
pause
