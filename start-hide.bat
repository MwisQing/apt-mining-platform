@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual env not found. Please run install.bat first.
    pause
    exit /b 1
)

if not exist "frontend\dist\index.html" (
    echo [ERROR] frontend\dist\index.html not found. The runtime package is incomplete.
    pause
    exit /b 1
)

:: Kill existing server on port 8088
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8088.*LISTENING" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo Starting APT Mining Workbench (hidden mode)...
echo Backend: http://127.0.0.1:8088
echo.

:: Use VBScript to launch the server with a hidden console window
set "VBS_FILE=%TEMP%\apt_mining_start.vbs"
(
    echo Set WshShell = CreateObject^("WScript.Shell"^)
    echo WshShell.CurrentDirectory = "%~dp0"
    echo WshShell.Run """%~dp0venv\Scripts\python.exe"" -m uvicorn backend.main:app --host 127.0.0.1 --port 8088", 0, False
) > "%VBS_FILE%"

wscript //nologo "%VBS_FILE%"
del "%VBS_FILE%"

:: Wait a moment for the server to start, then open browser
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8088

echo Server started in background. Close this window or visit http://127.0.0.1:8088
echo To stop the server, use Task Manager to kill python.exe or run: taskkill /IM python.exe /F
timeout /t 3 /nobreak >nul
