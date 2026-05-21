@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - Go Backend (Test)
echo ======================================
echo Port: 9099
echo DB: apt_mining_test
echo.

cd /d "%~dp0"

REM Load .env
for /f "tokens=1* delims==" %%a in ('findstr /v "^#" .env 2^>nul') do (
    set "%%a=%%b"
)

if "%APT_DB_PASSWORD_TEST%"=="" (
    echo [错误] .env 中 APT_DB_PASSWORD_TEST 未设置
    pause
    exit /b 1
)

cd /d "%~dp0backend_v2"
set APT_SERVER_PORT=9099
set APT_DB_NAME=%APT_DB_NAME_TEST%
set APT_DB_USER=%APT_DB_USER_TEST%
set APT_DB_PASSWORD=%APT_DB_PASSWORD_TEST%

echo [启动] Go 后端 (测试实例)...
echo.

start http://127.0.0.1:9099

if not exist "apt-mining.exe" (
    echo [错误] 未找到 backend_v2\apt-mining.exe
    pause
    exit /b 1
)

apt-mining.exe
