@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo APT Mining v4.0 — 初始化 PostgreSQL 数据库
echo ============================================
echo.

set "PG_BIN=C:\Program Files\PostgreSQL\18\bin\psql.exe"
set "PG_HOST=127.0.0.1"
set "PG_PORT=5432"

REM Load .env
cd /d "%~dp0"
for /f "tokens=1* delims==" %%a in ('findstr /v "^#" .env 2^>nul') do (
    set "%%a=%%b"
)

if "%1"=="--test" (
    echo [INFO] --test flag ignored. Database settings are managed in .env
)
set "PG_USER=%APT_DB_USER%"
set "PG_PASS=%APT_DB_PASSWORD%"
set "PG_DB=%APT_DB_NAME%"

if "%PG_PASS%"=="" (
    echo [错误] .env 中密码未设置
    pause
    exit /b 1
)

echo 数据库: %PG_DB%
echo.

REM 检查迁移文件
if not exist "backend_v2\migrations\001_initial.up.sql" (
    echo [ERROR] 迁移文件不存在: backend_v2\migrations\001_initial.up.sql
    pause
    exit /b 1
)

REM 创建数据库（如果不存在）
set PGPASSWORD=%PG_PASS%
"%PG_BIN%" -h %PG_HOST% -U %PG_USER% -d postgres -c "SELECT 1 FROM pg_database WHERE datname='%PG_DB%';" >nul 2>&1
if errorlevel 1 (
    echo [INFO] 创建数据库 %PG_DB%...
    "%PG_BIN%" -h %PG_HOST% -U %PG_USER% -d postgres -c "CREATE DATABASE %PG_DB%;"
)

REM 执行迁移
echo 正在执行迁移...
"%PG_BIN%" -h %PG_HOST% -U %PG_USER% -d %PG_DB% -f "backend_v2\migrations\001_initial.up.sql"

if errorlevel 1 (
    echo.
    echo [ERROR] 迁移执行失败
    pause
    exit /b 1
)

REM 验证表
echo.
echo 已创建的表：
set PGPASSWORD=%PG_PASS%
"%PG_BIN%" -h %PG_HOST% -U %PG_USER% -d %PG_DB% -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"

echo.
echo ============================================
echo 初始化完成！双击 startGo.bat 启动后端服务
echo ============================================
pause
