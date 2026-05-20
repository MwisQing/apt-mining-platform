@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - Go Backend
echo ======================================

python start.py --go --host 127.0.0.1
