@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0.."
echo ============================================
echo  Trading AI - first-time setup
echo ============================================
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found.
  echo Install Python 3.12 from https://www.python.org/downloads/
  echo and TICK "Add python.exe to PATH" on the first screen.
  pause
  exit /b 1
)
python -c "import sys; v=sys.version_info[:2]; print('Python', sys.version.split()[0]); sys.exit(0 if (3,11)<=v<=(3,13) else 1)"
if errorlevel 1 (
  echo [ERROR] Please use Python 3.11 or 3.12.
  pause
  exit /b 1
)
if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 ( echo [ERROR] Could not create .venv & pause & exit /b 1 )
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e python
if errorlevel 1 (
  echo [ERROR] Install failed. Copy the messages above and send them to Claude.
  pause
  exit /b 1
)
python -c "import MetaTrader5 as m; print('MetaTrader5 package', m.__version__, 'OK')"
if errorlevel 1 (
  echo [ERROR] MetaTrader5 package missing. Python 3.12 is the safest version.
  pause
  exit /b 1
)
echo.
echo Setup finished OK. Next: open MT5, log in, then run windows\1_check.bat
pause
