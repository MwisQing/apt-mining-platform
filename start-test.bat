@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo ======================================
echo APT Mining Workbench - Test Mode (9099)
echo ======================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual env not found. Please run install.bat first.
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo [ERROR] frontend\dist\index.html not found. The runtime package is incomplete.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [1/3] Switching vite proxy to 9099...
powershell -Command "(Get-Content 'frontend\vite.config.js') -replace 'http://127\.0\.0\.1:8088', 'http://127.0.0.1:9099' | Set-Content 'frontend\vite.config.js'"
echo      Done.

echo [2/3] Clearing port 9099...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9099.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo [3/3] Starting backend on port 9099...
echo Backend: http://127.0.0.1:9099
echo Press Ctrl+C to stop.
echo.
start "" http://127.0.0.1:9099
python -m uvicorn backend.main:app --host 127.0.0.1 --port 9099

REM Restore vite config on exit
powershell -Command "(Get-Content 'frontend\vite.config.js') -replace 'http://127\.0\.0\.1:9099', 'http://127.0.0.1:8088' | Set-Content 'frontend\vite.config.js'"
echo Vite proxy restored to 8088.

pause
