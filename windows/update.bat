@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
echo Getting the latest code from GitHub...
git pull
if errorlevel 1 ( echo [ERROR] git pull failed & pause & exit /b 1 )
if exist .venv\Scripts\activate.bat (
  call .venv\Scripts\activate.bat
  pip install -e python
)
echo Update finished.
pause
