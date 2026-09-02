@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

REM Быстрый дев-старт API+UI без пересборки фронтенда (для полной сборки — scripts\start.bat).
REM Окна называются hvk-api / hvk-ui, чтобы scripts\stop.bat находил их по заголовку.

netstat -ano | findstr ":8080" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo API already listening on :8080 - not starting a second instance.
) else (
  start "hvk-api" /MIN cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8080 > logs\api.log 2>&1"
)

netstat -ano | findstr ":8501" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo UI already listening on :8501 - not starting a second instance.
) else (
  start "hvk-ui" /MIN cmd /c ".venv\Scripts\python.exe -m uvicorn ui.static_server:app --host 0.0.0.0 --port 8501 > logs\ui.log 2>&1"
)

echo Done. Stop with scripts\stop.bat
