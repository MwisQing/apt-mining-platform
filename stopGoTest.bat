@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - Stop Go Test Backend
echo ======================================

powershell -NoProfile -Command "$port=9099; $procs=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; if ($procs.Count -eq 0) { Write-Host 'No running process on port' $port } else { foreach ($p in $procs) { Write-Host 'Stopping PID=' $p 'on port' $port; Stop-Process -Id $p -Force } }; Write-Host 'Done.'"
