@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo APT Mining v4.0 - Initialize PostgreSQL
echo ============================================
echo.

cd /d "%~dp0"

REM Load .env values when present. Defaults below match the Go/Python launchers.
if exist ".env" (
    for /f "tokens=1* delims==" %%a in ('findstr /v "^#" ".env" 2^>nul') do (
        set "%%a=%%b"
    )
) else (
    echo [WARN] .env not found. Using default local database settings.
)

if "%1"=="--test" (
    echo [INFO] --test flag ignored. Database settings are managed in .env
)

if "%PG_BIN%"=="" set "PG_BIN=psql"
if "%APT_DB_HOST%"=="" set "APT_DB_HOST=127.0.0.1"
if "%APT_DB_PORT%"=="" set "APT_DB_PORT=5432"
if "%APT_DB_USER%"=="" set "APT_DB_USER=apt_test"
if "%APT_DB_NAME%"=="" set "APT_DB_NAME=apt_mining_test"

set "PG_HOST=%APT_DB_HOST%"
set "PG_PORT=%APT_DB_PORT%"
set "PG_USER=%APT_DB_USER%"
set "PG_PASS=%APT_DB_PASSWORD%"
set "PG_DB=%APT_DB_NAME%"

if "%APT_DB_ADMIN_USER%"=="" (
    set "PG_ADMIN_USER=%PG_USER%"
) else (
    set "PG_ADMIN_USER=%APT_DB_ADMIN_USER%"
)

if "%APT_DB_ADMIN_PASSWORD%"=="" (
    set "PG_ADMIN_PASS=%PG_PASS%"
) else (
    set "PG_ADMIN_PASS=%APT_DB_ADMIN_PASSWORD%"
)

if not exist "%PG_BIN%" (
    where %PG_BIN% >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] psql was not found.
        echo Set PG_BIN to psql.exe or add PostgreSQL bin to PATH.
        pause
        exit /b 1
    )
)

echo Database: %PG_DB%
echo Host: %PG_HOST%:%PG_PORT%
echo User: %PG_USER%
echo Admin user for database creation: %PG_ADMIN_USER%
echo.

if not exist "backend_v2\migrations\001_initial.up.sql" (
    echo [ERROR] Migration file not found: backend_v2\migrations\001_initial.up.sql
    pause
    exit /b 1
)

set "PGPASSWORD=%PG_ADMIN_PASS%"
set "DB_EXISTS="
for /f "usebackq tokens=*" %%a in (`call "%PG_BIN%" -h "%PG_HOST%" -p "%PG_PORT%" -U "%PG_ADMIN_USER%" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='%PG_DB%';" 2^>nul`) do (
    set "DB_EXISTS=%%a"
)

if "%DB_EXISTS%"=="1" (
    echo [INFO] Database %PG_DB% already exists.
) else (
    echo [INFO] Creating database %PG_DB%...
    call "%PG_BIN%" -h "%PG_HOST%" -p "%PG_PORT%" -U "%PG_ADMIN_USER%" -d postgres -c "CREATE DATABASE ""%PG_DB%"";"
    if errorlevel 1 (
        echo.
        echo [ERROR] Database creation failed.
        echo Ensure %PG_ADMIN_USER% can connect to postgres and has CREATEDB permission.
        pause
        exit /b 1
    )
)

echo Running migrations...
set "PGPASSWORD=%PG_PASS%"
call "%PG_BIN%" -h "%PG_HOST%" -p "%PG_PORT%" -U "%PG_USER%" -d "%PG_DB%" -f "backend_v2\migrations\001_initial.up.sql"

if errorlevel 1 (
    echo.
    echo [ERROR] Migration failed.
    pause
    exit /b 1
)

echo.
echo Created tables:
call "%PG_BIN%" -h "%PG_HOST%" -p "%PG_PORT%" -U "%PG_USER%" -d "%PG_DB%" -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"

echo.
echo ============================================
echo Initialization complete. Run: python start.py
echo ============================================
pause
