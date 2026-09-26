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
echo !!! EMERGENCY: RiskGuard will close ALL positions and block trading !!!
choice /M "Are you sure"
if errorlevel 2 exit /b 0
python -m trading_ai kill
pause
