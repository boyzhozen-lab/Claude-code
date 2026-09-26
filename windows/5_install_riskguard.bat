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
echo Copying RiskGuard into MT5 and compiling it...
python -m trading_ai install-ea > reports\5_install.txt 2>&1
type reports\5_install.txt
echo.
echo Saved to reports\5_install.txt  - send it to Claude if it says FAILED.
pause
