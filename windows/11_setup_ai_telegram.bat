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
if not exist reports\logs mkdir reports\logs
if not exist .env copy .env.example .env >nul
echo ============================================================
echo  STEP 1: Notepad will open the file .env
echo    ANTHROPIC_API_KEY=sk-ant-...     (platform.claude.com - API Keys)
echo    TELEGRAM_BOT_TOKEN=123456:ABC... (Telegram - @BotFather - /newbot)
echo  Paste the values after the = signs, SAVE, then CLOSE Notepad.
echo ============================================================
start /wait notepad .env
echo.
echo ============================================================
echo  STEP 2: In Telegram, open your new bot and press START
echo          (or send it any message). Then press a key here.
echo ============================================================
pause
python -m trading_ai telegram-setup
echo.
python -m trading_ai ai-check
echo.
echo If both lines above say OK, run windows\12_setup_automation.bat
pause
