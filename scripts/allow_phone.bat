@echo off
chcp 65001 >nul
REM Один раз от администратора: телефон в той же Wi‑Fi сможет открыть интерфейс.
netsh advfirewall firewall delete rule name="HVK UI 8501" >nul 2>&1
netsh advfirewall firewall add rule name="HVK UI 8501" dir=in action=allow protocol=TCP localport=8501 profile=any
if errorlevel 1 (
  echo Не хватило прав. Правый клик по этому файлу — Запуск от имени администратора.
  exit /b 1
)
powershell -NoProfile -Command "Get-NetConnectionProfile | Set-NetConnectionProfile -NetworkCategory Private"
echo Готово. Телефон — в ту же Wi-Fi, что и этот компьютер, мобильный интернет выключить.
