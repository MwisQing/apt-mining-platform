@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ============================================
echo APT Mining v4.0 — Go 启动后端
echo ============================================
echo.

cd /d "%~dp0backend_v2"
if %errorlevel% neq 0 (
    echo [错误] 未找到 backend_v2 目录
    pause
    exit /b 1
)

echo [启动] Go 后端...
set APT_DB_NAME=apt_mining_prod
set APT_DB_USER=apt_prod
set APT_DB_PASSWORD=AptProd2026mining

echo.
apt-mining.exe
