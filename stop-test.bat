@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo ======================================
echo APT Mining Workbench - Stop Test Service
echo ======================================
echo.

set FOUND=0

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9099.*LISTENING" 2^>nul') do (
    set FOUND=1
    echo Stopping process on port 9099: %%a
    taskkill /PID %%a /F >nul 2>&1
)

if "%FOUND%"=="0" (
    echo No running service found on port 9099.
) else (
    echo Service stopped.
)

echo Restoring vite proxy to 8088...
if exist "frontend\vite.config.js" (
    powershell -Command "(Get-Content 'frontend\vite.config.js') -replace 'http://127\.0\.0\.1:9099', 'http://127.0.0.1:8088' | Set-Content 'frontend\vite.config.js'"
    echo Done.
) else (
    echo vite.config.js not found, skipping.
)

pause
