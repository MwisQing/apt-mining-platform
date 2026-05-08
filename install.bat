@echo off
echo ======================================
echo APT Mining Workbench - Install Runtime
echo ======================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ first.
    pause
    exit /b 1
)

node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 18+ first.
    pause
    exit /b 1
)

if not exist "venv\Scripts\activate.bat" (
    echo [1/5] Creating virtual environment...
    python -m venv venv
) else (
    echo [1/5] Virtual environment already exists.
)

call venv\Scripts\activate.bat

echo [2/5] Installing Python dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo [3/5] Installing frontend dependencies...
cd frontend
call npm install
if errorlevel 1 (
    echo [ERROR] Frontend dependency installation failed.
    cd ..
    pause
    exit /b 1
)

echo [4/5] Building frontend...
call npm run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed.
    cd ..
    pause
    exit /b 1
)
cd ..

echo [5/5] Checking database...
python -c "from backend.utils.db import init_db; init_db(); print('Database checked')"

echo.
echo ======================================
echo Done. Double-click start.bat to launch.
echo ======================================
pause
