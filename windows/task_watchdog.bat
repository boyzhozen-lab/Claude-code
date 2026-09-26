@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
if not exist reports\logs mkdir reports\logs
python -m trading_ai watchdog >> reports\logs\watchdog.log 2>&1
