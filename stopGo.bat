@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - Stop Go Backend
echo ======================================

powershell -NoProfile -Command "$port=8088; $procs=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; if ($procs.Count -eq 0) { Write-Host 'No running process on port' $port } else { foreach ($pid in $procs) { Write-Host 'Stopping PID=' $pid 'on port' $port; Stop-Process -Id $pid -Force } }; Write-Host 'Done.'"
