@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo Останавливаю окна Тихой редакции...

taskkill /FI "WINDOWTITLE eq hvk-brain*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq hvk-eyes*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq hvk-api*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq hvk-ui*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq hvk-bot*" /T /F >nul 2>&1

REM на случай, если заголовки не совпали — по портам
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000 .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8001 .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080 .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8501 .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1

echo Готово. Можно снова запускать scripts\start.bat
