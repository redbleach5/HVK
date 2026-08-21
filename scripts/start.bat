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

REM --- читаем пути из .env грубо через findstr ---
for /f "tokens=1,* delims==" %%A in ('findstr /B "LLAMA_SERVER_PATH=" .env 2^>nul') do set "LLAMA=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /B "BRAIN_GGUF_PATH=" .env 2^>nul') do set "BRAIN_GGUF=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /B "EYES_GGUF_PATH=" .env 2^>nul') do set "EYES_GGUF=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /B "EYES_MMPROJ_PATH=" .env 2^>nul') do set "EYES_MMPROJ=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /B "BRAIN_MODEL=" .env 2^>nul') do set "BRAIN_MODEL=%%B"
for /f "tokens=1,* delims==" %%A in ('findstr /B "EYES_MODEL=" .env 2^>nul') do set "EYES_MODEL=%%B"

if "%LLAMA%"=="" set "LLAMA=C:\llama.cpp\llama-server.exe"
if "%BRAIN_GGUF%"=="" set "BRAIN_GGUF=C:\models\qwen3.8-27b-q4_k_m.gguf"
if "%EYES_GGUF%"=="" set "EYES_GGUF=C:\models\gemma4-12b-q5_k_m.gguf"
if "%EYES_MMPROJ%"=="" set "EYES_MMPROJ=C:\models\gemma4-12b-mmproj.gguf"
if "%BRAIN_MODEL%"=="" set "BRAIN_MODEL=qwen-27b"
if "%EYES_MODEL%"=="" set "EYES_MODEL=gemma-12b"

echo Запускаю текстовую модель на :8000...
start "hvk-brain" /MIN "%LLAMA%" -m "%BRAIN_GGUF%" --port 8000 --host 127.0.0.1 --fit --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 -c 32768 --alias %BRAIN_MODEL%
timeout /t 2 /nobreak >nul

echo Запускаю фото-модель на :8001...
start "hvk-eyes" /MIN "%LLAMA%" -m "%EYES_GGUF%" --mmproj "%EYES_MMPROJ%" --port 8001 --host 127.0.0.1 --fit --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0 -c 16384 --mmproj-offload --alias %EYES_MODEL%
timeout /t 2 /nobreak >nul

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
echo Тихая редакция запущена.
echo На этом ПК:  http://127.0.0.1:8501
echo С другого устройства в сети: http://IP-этого-ПК:8501
echo (API и модели слушают только localhost — так и нужно.)
echo Для остановки — scripts\stop.bat
endlocal
