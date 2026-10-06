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
set OUT=reports\13_intraday_momentum.txt
echo Updating M15 bars for US indices...
python -m trading_ai fetch-bars --symbols SPX500 NAS100 DOW30 --timeframes M15 > %OUT% 2>&1
echo. >> %OUT%
echo ===== INTRADAY MOMENTUM (last half hour, walk-forward) ===== >> %OUT%
python -m trading_ai backtest --strategy intraday_momentum --walk-forward >> %OUT% 2>&1
echo. >> %OUT%
echo ===== COMBINED WITH RSI2 (correlation + challenge) ===== >> %OUT%
python -m trading_ai backtest --strategy rsi2_reversion intraday_momentum --walk-forward >> %OUT% 2>&1
python -m trading_ai challenge --strategy rsi2_reversion intraday_momentum --walk-forward --risks 0.5 0.75 1.0 1.25 >> %OUT% 2>&1
type %OUT%
echo.
echo Saved to %OUT%  - send this file to Claude.
pause
