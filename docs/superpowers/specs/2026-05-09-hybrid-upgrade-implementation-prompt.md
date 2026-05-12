# APT Mining Workbench — 混合模式一键升级系统 实现提示词

> 把本文件完整粘贴给 AI，让它在项目根目录下执行。

---

## 你的角色

你是一个 Windows 批处理脚本开发者。你需要在 APT Mining Workbench 项目中实现一套"混合模式一键升级系统"。项目是 FastAPI + Vue 3 + SQLite 的单机离线平台，运行在 Windows 上。

## 项目背景

- 开发环境在本机（迭代快，AI 开发，用脱敏测试数据）
- 正式环境在另一台 Windows 机器上（敏感数据，其他同事操作）
- 正式环境可能联网（可 git pull）也可能离线（需 zip 包）
- 需要一套机制让正式环境安全同步到最新代码，绝不影响数据

## 核心原则

1. **数据零风险** — `data/`、`uploads/`、`backups/` 在任何操作中都不被删除、覆盖、移动
2. **操作极简** — 同事只需"双击 .bat"
3. **双通道分发** — 联网走 git pull，离线走 zip 包，正式侧自动检测
4. **升级前自动备份** — 每次升级前备份 DB

## 当前项目结构

```
apt-mining-platform-v3.1/
├── backend/                    # FastAPI 后端 Python 代码
├── frontend/                   # Vue 3 前端
│   ├── src/                    # 源码
│   ├── dist/                   # 构建产物（npm run build 生成）
│   ├── node_modules/
│   └── package.json
├── config/                     # 配置文件（config.yaml 等）
├── data/                       # SQLite 数据库（workbench.db）
├── uploads/                    # 上传的 Excel 文件
├── backups/                    # DB 备份
├── venv/                       # Python 虚拟环境
├── start.bat                   # 启动平台
├── install.bat                 # 首次安装
├── start-hide.bat              # 【要删除】
├── update.bat                  # 【要删除，功能合并到 upgrade.bat】
├── VERSION                     # 内容为单行版本号，如 "3.1"
├── CHANGELOG.md
├── requirements.txt
└── .gitignore
```

## 需要完成的任务

### 任务 1：创建 `一键打包.bat`（开发侧使用）

在项目根目录创建 `一键打包.bat`，用于打 zip 发布包。

**完整流程：**

```
1. @echo off + chcp 65001 >nul 2>&1 + setlocal enabledelayedexpansion
2. 读取 VERSION 文件内容到变量 OLD_VER
3. 显示标题和当前版本
4. 提示用户输入新版本号，默认为当前版本的最后一位 +1
   - 例如 3.1 → 默认 3.1.1，3.1.3 → 默认 3.1.4
   - 用户直接回车则使用默认值
5. 将新版本号写入 VERSION
6. 检查 frontend\package.json 是否存在
7. cd frontend && call npm run build
   - 如果构建失败，显示错误并 pause + exit
   - cd ..
8. 创建 releases\ 目录（如不存在）
9. 创建临时目录 _release_tmp\
10. 用 robocopy 复制项目到 _release_tmp\，排除以下目录和文件：
    /XD: data uploads backups venv node_modules .git .claude __pycache__ releases _release_tmp
    /XF: *.pyc tmp_*.db *_regression.db
11. 用 PowerShell Compress-Archive 将 _release_tmp\ 压缩为 releases\apt-mining-v{版本号}.zip
    - 如果同名 zip 已存在，先删除
12. 删除 _release_tmp\（rmdir /S /Q）
13. 显示 zip 路径
14. pause
```

**输出格式：**
```
======================================
APT Mining Workbench - 一键打包
======================================
当前版本: 3.1
请输入新版本号 [3.1.1]:
[1/3] 更新版本号... 3.1.1
[2/3] 构建前端... 完成
[3/3] 打包发布... 完成

发布包: releases\apt-mining-v3.1.1.zip
请将此文件发送给正式环境。
======================================
```

### 任务 2：创建 `一键上传.bat`（开发侧使用）

在项目根目录创建 `一键上传.bat`，用于 git 提交和推送。

**完整流程：**

```
1. @echo off + chcp 65001 >nul 2>&1 + setlocal enabledelayedexpansion
2. 检测 git 是否可用（where git >nul 2>&1）
   - 不可用 → 显示错误，pause + exit
3. 执行 git status --short，捕获输出
4. 如果输出为空，显示"没有需要提交的变更"，pause + exit
5. 显示标题
6. 执行 git status --short 显示变更文件列表
7. echo. 空行
8. 提示用户输入提交说明（set /p COMMIT_MSG=请输入提交说明: ）
   - 如果为空，显示"提交说明不能为空"，pause + exit
9. git add -A
10. git commit -m "%COMMIT_MSG%"
    - 失败 → 显示错误，pause + exit
11. git push origin main
    - 失败 → 显示"推送失败，请检查网络和远程仓库"，pause + exit
12. 读取 VERSION 到变量 VER
13. 检查 tag v%VER% 是否已存在（git tag -l "v%VER%"）
    - 不存在 → git tag v%VER% + git push --tags
    - 已存在 → 显示"标签 v%VER% 已存在，跳过"
14. 显示完成信息
15. pause
```

**输出格式：**
```
======================================
APT Mining Workbench - 一键上传
======================================
变更文件:
 M backend/api/alerts.py
 M frontend/src/views/Workbench.vue

请输入提交说明: 修复表头排序bug

[1/3] 提交代码... 完成
[2/3] 推送到远程... 完成
[3/3] 创建标签 v3.1.1... 完成

代码已推送，正式环境可执行 upgrade.bat 拉取。
======================================
```

### 任务 3：创建 `upgrade.bat`（正式侧使用，随代码分发）

在项目根目录创建 `upgrade.bat`，正式环境同事双击即可升级。

**完整流程：**

```
1. @echo off + chcp 65001 >nul 2>&1 + setlocal enabledelayedexpansion
2. 显示标题
3. 读取 VERSION 到 OLD_VER（文件不存在则设为"未知"）
4. 显示当前版本

5. [备份数据库]
   - 检查 data\workbench.db 是否存在
   - 存在 → mkdir backups（如不存在）
   - 用 wmic 获取时间戳 YYYYMMDD_HHMMSS
   - copy data\workbench.db backups\workbench_%时间戳%.db
   - 保存备份路径到变量 BACKUP_PATH
   - 不存在 → 显示"数据库不存在，跳过备份"

6. [检测升级方式 — 优先 ZIP]
   a. 扫描当前目录下 apt-mining-v*.zip 文件
      - 找到 → 设 MODE=ZIP，记录文件名
      - 找到多个 → 取最后一个（dir /B /O:N 排序，最后一个是版本最大的）
   b. 没有 zip → 检测 git
      - where git 成功 且 git remote 有输出 → 设 MODE=GIT
      - git fetch origin
        - 失败 → 显示网络错误，pause + exit
      - 比较 HEAD vs origin/main
        - 相同 → 显示"代码已是最新"，跳到依赖安装步骤
        - 不同 → git pull origin main
   c. 既没有 zip 也没有 git → 显示提示并 pause + exit：
      "未找到升级包，也未检测到 Git。
       请将 apt-mining-v*.zip 放到当前目录后重试，
       或配置 Git 远程仓库。"

7. [ZIP 模式解压]（仅 MODE=ZIP 时执行）
   - 用 PowerShell Expand-Archive 解压到 _upgrade_tmp\
     powershell -Command "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '_upgrade_tmp' -Force"
   - 检测 _upgrade_tmp 内是否有单层嵌套目录（zip 可能包一层目录）
     - 如果 _upgrade_tmp 下只有一个子目录且该子目录包含 VERSION 文件 → 使用该子目录作为源
     - 否则 → 直接用 _upgrade_tmp 作为源
   - robocopy %SOURCE% .\ /E /IS /IT /NFL /NDL /NJH /NJS
     /XD data uploads backups venv node_modules .git .claude _upgrade_tmp releases
   - rmdir /S /Q _upgrade_tmp
   - 移动已用的 zip 到 releases\（mkdir releases 如不存在）

8. [安装后端依赖]
   - 检查 venv\Scripts\activate.bat 是否存在
   - 存在 → call venv\Scripts\activate.bat → pip install -r requirements.txt -q
   - 不存在 → 显示"venv 不存在，请先运行 install.bat"，pause + exit

9. [安装前端依赖 + 构建]
   - 检查 frontend\package.json 是否存在
   - cd frontend
   - call npm install --silent 2>nul
   - call npm run build
   - 如果构建失败 → 显示警告但不退出
   - cd ..

10. [显示结果]
    - 读取新 VERSION 到 NEW_VER
    - 显示 OLD_VER → NEW_VER
    - 显示备份路径（如果有）
    - 提示运行 start.bat

11. pause
```

**输出格式（ZIP 模式）：**
```
======================================
APT Mining Workbench - 一键升级
======================================
当前版本: 3.1

[1/5] 备份数据库... 已备份: backups\workbench_20260509_143022.db
[2/5] 检测升级方式... 离线包模式
      找到升级包: apt-mining-v3.1.1.zip
      正在解压覆盖代码...（数据目录已保护）
      代码更新完成。
[3/5] 安装后端依赖... 完成
[4/5] 构建前端... 完成
[5/5] 版本确认... 3.1 → 3.1.1

======================================
升级完成！请运行 start.bat 启动平台。
如需回滚，备份文件: backups\workbench_20260509_143022.db
======================================
```

**输出格式（GIT 模式）：**
```
======================================
APT Mining Workbench - 一键升级
======================================
当前版本: 3.1

[1/5] 备份数据库... 已备份: backups\workbench_20260509_143022.db
[2/5] 检测升级方式... Git 模式
      检测到新版本，正在拉取...
      代码更新完成。
[3/5] 安装后端依赖... 完成
[4/5] 构建前端... 完成
[5/5] 版本确认... 3.1 → 3.1.1

======================================
升级完成！请运行 start.bat 启动平台。
如需回滚，备份文件: backups\workbench_20260509_143022.db
======================================
```

### 任务 4：删除旧文件

- 删除 `start-hide.bat`
- 删除 `update.bat`

### 任务 5：修改 `.gitignore`

在 `.gitignore` 末尾添加：

```
# Release packages
releases/
```

### 任务 6：验证

完成后执行以下验证：

1. 在开发环境运行 `一键打包.bat`，确认：
   - VERSION 被更新
   - releases/ 下生成了 zip 文件
   - zip 内不包含 data/、uploads/、backups/、venv/、node_modules/、.git/
2. 检查 `一键上传.bat` 语法正确（不需要真正 push）
3. 检查 `upgrade.bat` 语法正确
4. 确认 `start-hide.bat` 和 `update.bat` 已删除
5. 确认 `.gitignore` 包含 `releases/`

## 注意事项

- 所有 .bat 文件必须以 `@echo off` 开头，`chcp 65001 >nul 2>&1` 设置 UTF-8
- 使用 `setlocal enabledelayedexpansion`，变量在 if/for 块内用 `!VAR!` 而非 `%VAR%`
- 中文输出必须正常显示（文件保存为 UTF-8 with BOM 或确保 chcp 65001 生效）
- robocopy 成功退出码是 0-7（不是只有 0），需要判断 `errorlevel` 是否 > 7 才算失败
- PowerShell 命令用 `powershell -Command "..."` 调用
- 路径中不要使用 Unix 风格的 `/`，一律用 Windows 的 `\`
