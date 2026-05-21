@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - Go Backend
echo ======================================
echo Port: 8088
echo DB: apt_mining_prod
echo.

cd /d "%~dp0"

REM Load .env
for /f "tokens=1* delims==" %%a in ('findstr /v "^#" .env 2^>nul') do (
    set "%%a=%%b"
)

if "%APT_DB_PASSWORD_PROD%"=="" (
    echo [错误] .env 中 APT_DB_PASSWORD_PROD 未设置
    pause
    exit /b 1
)

cd /d "%~dp0backend_v2"
set APT_DB_NAME=%APT_DB_NAME_PROD%
set APT_DB_USER=%APT_DB_USER_PROD%
set APT_DB_PASSWORD=%APT_DB_PASSWORD_PROD%

echo [启动] Go 后端...
echo.

start http://127.0.0.1:8088

if not exist "apt-mining.exe" (
    echo [错误] 未找到 backend_v2\apt-mining.exe
    echo 请先运行 python install.py 构建，或使用 python start.py 自动编译后启动。
    pause
    exit /b 1
)

apt-mining.exe
