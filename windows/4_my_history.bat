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
echo Reading your closed trades from the MT5 account that is logged in now.
echo (Read-only: nothing is opened or closed.)
python -m trading_ai import-history --days 1500 > reports\4_my_history.txt 2>&1
python -m trading_ai stats --by symbol session weekday trend_d1 exit_reason direction >> reports\4_my_history.txt 2>&1
type reports\4_my_history.txt
echo.
echo Saved to reports\4_my_history.txt
pause
