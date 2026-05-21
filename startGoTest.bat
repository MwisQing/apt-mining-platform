@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - Go Backend (Test)
echo ======================================
echo Port: 9099
echo DB: apt_mining_test
echo.

cd /d "%~dp0backend_v2"
if %errorlevel% neq 0 (
    echo [错误] 未找到 backend_v2 目录
    pause
    exit /b 1
)

set APT_SERVER_PORT=9099
set APT_DB_NAME=apt_mining_test
set APT_DB_USER=apt_test
set APT_DB_PASSWORD=AptTest2026mining

echo [启动] Go 后端 (测试实例)...
echo.

start http://127.0.0.1:9099

apt-mining.exe
