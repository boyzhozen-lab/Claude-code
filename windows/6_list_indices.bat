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
python -m trading_ai list-symbols ind > reports\6_indices.txt 2>&1
type reports\6_indices.txt
echo.
echo Saved to reports\6_indices.txt  - send it to Claude.
pause
