@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - 代码更新
echo ======================================
echo.

:: Step 1: Check git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 git，请先安装 git。
    pause
    exit /b 1
)

:: Step 2: Backup database (safety measure before any code change)
echo [1/4] 备份数据库...
if exist "data\workbench.db" (
    if not exist "backups" mkdir backups
    for /f "tokens=2 delims==" %%a in ('wmic OS GetLocalDateTime /value') do set "dt=%%a"
    set "backup_name=backups\workbench_%dt:~0,4%%dt:~4,2%%dt:~6,2%_%dt:~8,2%%dt:~10,2%%dt:~12,2%.db"
    copy "data\workbench.db" "%backup_name%" >nul 2>&1
    echo  已备份: %backup_name%
) else (
    echo  数据库不存在，跳过备份。
)

:: Step 3: Git pull
echo [2/4] 拉取最新代码...
git fetch origin >nul 2>&1
if %errorlevel% neq 0 (
    echo  [警告] git fetch 失败，请检查网络连接和远程仓库。
    pause
    exit /b 1
)

git rev-parse HEAD > "%TEMP%\ale_local.txt" 2>nul
git rev-parse origin/main > "%TEMP%\ale_remote.txt" 2>nul
set "LOCAL="
set "REMOTE="
for /f %%a in (%TEMP%\ale_local.txt) do set "LOCAL=%%a"
for /f %%a in (%TEMP%\ale_remote.txt) do set "REMOTE=%%a"
del "%TEMP%\ale_local.txt" "%TEMP%\ale_remote.txt" 2>nul

if "!LOCAL!"=="!REMOTE!" (
    echo  代码已是最新。
) else (
    echo  检测到新版本，正在拉取...
    git pull origin main
    if !errorlevel! neq 0 (
        echo  [错误] git pull 失败，请手动处理。
        pause
        exit /b 1
    )
    echo  代码更新完成。
)

:: Step 4: Install dependencies
echo [3/4] 检查依赖...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    pip install -r requirements.txt -q
    echo  后端依赖安装完成。
) else (
    echo  [警告] venv 不存在，请先运行 install.bat。
)

if exist "frontend\package.json" (
    cd frontend
    call npm install --silent 2>nul
    echo  前端依赖安装完成。
    cd ..
)

:: Step 5: Build frontend
echo [4/4] 构建前端...
if exist "frontend\package.json" (
    cd frontend
    call npm run build
    if !errorlevel! neq 0 (
        echo  [警告] 前端构建失败，请手动执行 npm run build。
    ) else (
        echo  前端构建完成。
    )
    cd ..
)

echo.
echo ======================================
echo 代码更新完成！
echo 数据库迁移将在启动时自动执行。
echo 请运行 start.bat 启动平台。
echo ======================================
pause
