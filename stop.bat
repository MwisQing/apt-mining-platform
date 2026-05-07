@echo off
echo ======================================
echo APT Mining Workbench - Stop Service
echo ======================================
echo.

set FOUND=0

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8088.*LISTENING" 2^>nul') do (
    set FOUND=1
    echo Stopping process on port 8088: %%a
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING" 2^>nul') do (
    set FOUND=1
    echo Stopping legacy process on port 8000: %%a
    taskkill /PID %%a /F >nul 2>&1
)

if "%FOUND%"=="0" (
    echo No running service found on port 8088 or 8000.
) else (
    echo Service stopped.
)

pause
