@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo Создаю виртуальное окружение...
  python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Создала .env из примера — заполни токены при желании.
)

if not exist "pids.json" (
  echo {}> pids.json
)

set "PIDFILE=%cd%\pids.json"
set "LOGDIR=%cd%\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM --- Ollama уже запущен, модели не нужны ---

echo Запускаю API на :8080...
start "hvk-api" /MIN cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080 > logs\api.log 2>&1"

timeout /t 3 /nobreak >nul

echo Запускаю интерфейс Streamlit...
start "hvk-ui" /MIN cmd /c ".venv\Scripts\streamlit.exe run ui\app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true > logs\ui.log 2>&1"

findstr /B "TELEGRAM_BOT_TOKEN=" .env | findstr /V /C:"TELEGRAM_BOT_TOKEN=$" | findstr /V /C:"TELEGRAM_BOT_TOKEN= " >nul
if not errorlevel 1 (
  echo Запускаю Telegram-бота...
  start "hvk-bot" /MIN cmd /c ".venv\Scripts\python.exe -m bot.main > logs\bot.log 2>&1"
)

echo.
echo Тихая редакция запущена (Ollama).
echo На этом ПК:  http://127.0.0.1:8501
echo С другого устройства в сети: http://IP-этого-ПК:8501
echo (API слушает только localhost — так и нужно.)
echo Для остановки — scripts\stop.bat
endlocal
