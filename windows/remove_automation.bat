@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
schtasks /Delete /F /TN "TradingAI\Watchdog"
schtasks /Delete /F /TN "TradingAI\Daily"
schtasks /Delete /F /TN "TradingAI\Weekly"
echo Scheduled tasks removed.
pause
