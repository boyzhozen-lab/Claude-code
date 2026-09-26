@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
set ROOT=%CD%
set VBS=%ROOT%\windows\run_hidden.vbs
echo Creating scheduled tasks (they run hidden, only while you are logged in)...
schtasks /Create /F /TN "TradingAI\Watchdog" /SC MINUTE /MO 10 /TR "wscript.exe \"%VBS%\" \"%ROOT%\windows\task_watchdog.bat\""
schtasks /Create /F /TN "TradingAI\Daily" /SC DAILY /ST 07:40 /TR "wscript.exe \"%VBS%\" \"%ROOT%\windows\task_daily.bat\""
schtasks /Create /F /TN "TradingAI\Weekly" /SC WEEKLY /D SAT /ST 09:10 /TR "wscript.exe \"%VBS%\" \"%ROOT%\windows\task_weekly.bat\""
echo.
echo Done:
echo   every 10 min  : watchdog (alerts + new/closed trades to Telegram)
echo   daily 07:40   : update code from GitHub + daily report
echo   Saturday 09:10: weekly report with AI analysis
echo Remove them any time with windows\remove_automation.bat
echo.
echo Running the watchdog once now...
call windows\task_watchdog.bat
type reports\logs\watchdog.log
pause
