@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
if not exist reports\logs mkdir reports\logs
echo ===== %DATE% %TIME% ===== >> reports\logs\weekly.log
python -m trading_ai report --period weekly >> reports\logs\weekly.log 2>&1
python -m trading_ai forward-check >> reports\logs\weekly.log 2>&1
