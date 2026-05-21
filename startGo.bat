@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - Go Backend
echo ======================================
echo Port: 8088
echo DB: apt_mining_prod
echo.

cd /d "%~dp0backend_v2"
if %errorlevel% neq 0 (
    echo [错误] 未找到 backend_v2 目录
    pause
    exit /b 1
)

set APT_DB_NAME=apt_mining_prod
set APT_DB_USER=apt_prod
set APT_DB_PASSWORD=AptProd2026mining

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
