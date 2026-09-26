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
echo Downloading price history (can take several minutes)...
python -m trading_ai fetch-bars > reports\2_fetch.txt 2>&1
python -m trading_ai validate-bars >> reports\2_fetch.txt 2>&1
type reports\2_fetch.txt
echo.
echo Saved to reports\2_fetch.txt
pause
