@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
call .venv\Scripts\activate.bat
if not exist reports\logs mkdir reports\logs
echo ===== %DATE% %TIME% ===== >> reports\logs\daily.log
git pull --ff-only >> reports\logs\daily.log 2>&1
if errorlevel 1 python -m trading_ai notify "Auto-update from GitHub failed. Please run windows\update.bat and send the message to Claude." >> reports\logs\daily.log 2>&1
pip install -q -e python >> reports\logs\daily.log 2>&1
python -m trading_ai report --period daily >> reports\logs\daily.log 2>&1
