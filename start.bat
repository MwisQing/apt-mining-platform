@echo off
echo ======================================
echo APT Mining Workbench - Starting
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

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8088.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo Backend: http://127.0.0.1:8088
echo Press Ctrl+C to stop.
echo.
start "" http://127.0.0.1:8088
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8088

pause
