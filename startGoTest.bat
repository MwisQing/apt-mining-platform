@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - Go Backend (Test)
echo ======================================
echo Port: 9099
echo DB: apt_mining_test
echo.

python start.py --go --test
