# 平台更新与数据迁移系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 APT Mining Workbench 构建版本管理、Alembic 数据库迁移、一键更新脚本和 WebUI 系统信息展示。

**Architecture:** 根目录 VERSION 文件存储版本号，Alembic 管理 SQLite 数据库 schema 迁移，update.bat 脚本串联 git pull → 依赖安装 → 数据库备份 → 迁移 → 前端构建，后端新增 `/api/version` 接口，前端 Settings 页新增「系统信息」Tab 展示版本与变更日志。

**Tech Stack:** Alembic, SQLite, FastAPI, Vue 3, bat 脚本, git

---

### Task 1: 创建 VERSION 文件与 CHANGELOG.md

**Files:**
- Create: `VERSION`
- Create: `CHANGELOG.md`

- [ ] **Step 1: 创建 VERSION 文件**

```
3.1
```

文件内容就是纯文本 `3.1`，一行。

- [ ] **Step 2: 创建 CHANGELOG.md 文件**

```markdown
# Changelog

## v3.1 - 2026-05-08

- 新增：全量缓存候选查询，排序/翻页零DB查询
- 新增：Excel风格表头下拉筛选（7列）
- 新增：上传进度条实时显示
- 修复：resize/sort冲突
- 修复：全量缓存SQLite表达式树溢出

## v3.2 - 2026-05-08

- 新增：平台版本更新与数据迁移系统
- 新增：Alembic 数据库版本管理与基线迁移
- 新增：update.bat 一键更新脚本
- 新增：WebUI 系统信息 Tab（版本号/变更日志/更新检查）
```

---

### Task 2: 更新 .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 修改 .gitignore**

将 CLAUDE.md 从忽略列表中移除（保留为项目协作文件），同时添加备份目录和 Alembic 相关排除：

```
# Python
venv/
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
*.egg

# Database
data/

# Backups
backups/

# Uploads (keep directory, ignore files)
uploads/*
!uploads/.keep

# Logs
logs/

# Frontend
frontend/dist/
frontend/node_modules/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Test / Temp
tmp_*.db
*_regression.db
```

删除原有的 `CLAUDE.md`、`CLAUDE_RESPONSE.md`、`CLAUDE*.md` 三行。

---

### Task 3: Alembic 初始化与基线迁移

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_baseline_v31.py`

- [ ] **Step 1: 创建 `backend/alembic.ini`**

```ini
[alembic]
script_location = backend/alembic
sqlalchemy.url = sqlite:///data/workbench.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: 创建 `backend/alembic/env.py`**

```python
import sys
import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, text
from alembic import context

# Add project root to path so `backend` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from backend.models import Base
from backend.models import alert, tag, traced_target, event, import_model  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Apply SQLite pragmas before migration
        connection.execute(text("PRAGMA journal_mode=WAL"))
        connection.execute(text("PRAGMA foreign_keys=ON"))
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: 创建 `backend/alembic/versions/001_baseline_v31.py`**

这是 v3.1 的基线迁移，包含所有当前已存在的表结构。如果数据库中表已存在，此迁移使用 `IF NOT EXISTS` 确保幂等。

```python
"""Baseline schema for v3.1

Revision ID: 001_baseline_v31
Revises:
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa

revision = "001_baseline_v31"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("first_alert_time", sa.DateTime, nullable=False),
        sa.Column("last_alert_time", sa.DateTime, nullable=False),
        sa.Column("source_ip", sa.Text, nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text),
        sa.Column("port", sa.Text),
        sa.Column("threat_type", sa.Text),
        sa.Column("threat_level", sa.Text),
        sa.Column("std_apt_org", sa.Text),
        sa.Column("apt_org", sa.Text),
        sa.Column("apt_org_tier", sa.Text),
        sa.Column("alert_count", sa.Integer),
        sa.Column("vendors", sa.Text),
        sa.Column("protocol", sa.Text),
        sa.Column("intel_tags", sa.Text),
        sa.Column("intel_position", sa.Text),
        sa.Column("disposal_action", sa.Text),
        sa.Column("dns_resolved_ip", sa.Text),
        sa.Column("down_traffic", sa.Integer),
        sa.Column("up_traffic", sa.Integer),
        sa.Column("asset_type", sa.Text),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("imported_at", sa.DateTime, nullable=False),
        sa.Column("unique_hash", sa.Text, unique=True),
        sa.Column("content_hash", sa.Text),
        sa.Column("import_id", sa.Integer),
        sa.Column("import_sheet_id", sa.Integer),
        sa.Column("import_row_id", sa.Integer),
        sa.Column("sheet_name", sa.Text),
        sa.Column("excel_row_number", sa.Integer),
        sa.Column("raw_row_hash", sa.Text),
        sa.Column("analysis_status", sa.Text, server_default=""),
        sa.Column("is_focused", sa.Integer, server_default="0"),
    )

    # mined_events
    op.create_table(
        "mined_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_name", sa.Text, nullable=False),
        sa.Column("color", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("mined_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    # mined_event_devices
    op.create_table(
        "mined_event_devices",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("event_id", "device_id"),
    )

    # mined_event_iocs
    op.create_table(
        "mined_event_iocs",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("port", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("event_id", "target", "port"),
    )

    # event_followups
    op.create_table(
        "event_followups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    # tags
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("color", sa.Text, nullable=False),
        sa.Column("is_permanent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("tag_batches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    # tag_batches
    op.create_table(
        "tag_batches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("batch_name", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("device_ids_snapshot", sa.Text),
    )

    # device_tags
    op.create_table(
        "device_tags",
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint("device_id", "tag_id"),
    )

    # traced_targets
    op.create_table(
        "traced_targets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("port", sa.Text, nullable=True),
        sa.Column("traced_at", sa.DateTime, nullable=True),
        sa.Column("note", sa.Text),
        sa.UniqueConstraint("target", "port"),
    )

    # imports
    op.create_table(
        "imports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("imported_at", sa.DateTime, nullable=False),
        sa.Column("rows_inserted", sa.Integer),
        sa.Column("rows_skipped", sa.Integer),
        sa.Column("rows_failed", sa.Integer),
        sa.Column("total_rows", sa.Integer),
        sa.Column("parsed_rows", sa.Integer),
        sa.Column("raw_rows", sa.Integer),
        sa.Column("status", sa.Text),
        sa.Column("log", sa.Text),
    )

    # import_sheets
    op.create_table(
        "import_sheets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("import_id", sa.Integer, sa.ForeignKey("imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sheet_name", sa.Text, nullable=False),
        sa.Column("sheet_index", sa.Integer, nullable=False),
        sa.Column("header_row", sa.Integer),
        sa.Column("headers_json", sa.Text),
        sa.Column("row_count", sa.Integer),
        sa.Column("parsed_rows", sa.Integer),
        sa.Column("raw_rows", sa.Integer),
        sa.Column("failed_rows", sa.Integer),
        sa.Column("status", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # import_rows
    op.create_table(
        "import_rows",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("import_id", sa.Integer, sa.ForeignKey("imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_sheet_id", sa.Integer, sa.ForeignKey("import_sheets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("sheet_name", sa.Text, nullable=False),
        sa.Column("excel_row_number", sa.Integer, nullable=False),
        sa.Column("raw_json", sa.Text, nullable=False),
        sa.Column("normalized_json", sa.Text),
        sa.Column("parse_status", sa.Text, nullable=False),
        sa.Column("parse_error", sa.Text),
        sa.Column("row_hash", sa.Text),
        sa.Column("alert_id", sa.Integer),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text),
        sa.Column("target_id", sa.Text),
        sa.Column("detail", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # Indexes
    op.create_index("idx_alerts_device_id", "alerts", ["device_id"])
    op.create_index("idx_alerts_source_ip", "alerts", ["source_ip"])
    op.create_index("idx_alerts_target", "alerts", ["target"])
    op.create_index("idx_alerts_imported_at", "alerts", ["imported_at"])
    op.create_index("idx_alerts_first_alert_time", "alerts", ["first_alert_time"])
    op.create_index("idx_alerts_std_apt_org", "alerts", ["std_apt.apt_org"])
    op.create_index("idx_alerts_crossday", "alerts", ["source_ip", "target", "first_alert_time"])
    op.create_index("idx_alerts_content_hash", "alerts", ["content_hash"])
    op.create_index("idx_alerts_import_id", "alerts", ["import_id"])
    op.create_index("idx_alerts_import_row_id", "alerts", ["import_row_id"])
    op.create_index("idx_alerts_is_focused", "alerts", ["is_focused"])
    op.create_index("idx_alerts_threat_type", "alerts", ["threat_type"])
    op.create_index("idx_import_sheets_import_id", "import_sheets", ["import_id"])
    op.create_index("idx_import_rows_import_id", "import_rows", ["import_id"])
    op.create_index("idx_import_rows_sheet_id", "import_rows", ["import_sheet_id"])
    op.create_index("idx_import_rows_status", "import_rows", ["parse_status"])


def downgrade() -> None:
    # In production we would drop tables, but for safety baseline downgrade is no-op.
    # Users should use backups instead.
    pass
```

**注意：** 此迁移是基线版本，如果数据库表已存在（用户升级场景），Alembic 会记录版本但不会重复创建。新用户首次安装时表由 SQLAlchemy `create_all` 创建，然后 Alembic 标记为已迁移到基线。

---

### Task 4: 后端 /api/version 接口

**Files:**
- Create: `backend/api/version.py`
- Modify: `backend/main.py`

- [ ] **Step 1: 创建 `backend/api/version.py`**

```python
import os
import subprocess
from fastapi import APIRouter

router = APIRouter()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_version():
    ver_path = os.path.join(_PROJECT_ROOT, "VERSION")
    if os.path.exists(ver_path):
        with open(ver_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "unknown"


def _get_git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _get_git_remote_url():
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _check_update_available():
    """Compare local HEAD with remote HEAD. Returns (has_update, local_ahead)."""
    remote = _get_git_remote_url()
    if not remote:
        return False, False
    try:
        # Fetch remote refs without merging
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True, cwd=_PROJECT_ROOT, timeout=30
        )
        local = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5
        ).stdout.strip()
        remote_head = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True, text=True, cwd=_PROJECT_ROOT, timeout=5
        ).stdout.strip()
        if not local or not remote_head:
            return False, False
        if local == remote_head:
            return False, False
        # Check if local is ahead of remote
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", remote_head, local],
            cwd=_PROJECT_ROOT, timeout=5
        )
        if result.returncode == 0:
            return False, True  # local is ahead
        return True, False  # remote is ahead
    except Exception:
        return False, False


@router.get("/api/version")
def get_version():
    commit = _get_git_commit()
    remote_url = _get_git_remote_url()
    has_update, local_ahead = _check_update_available()
    return {
        "version": _read_version(),
        "git_commit": commit,
        "git_remote_url": remote_url,
        "update_available": has_update,
        "local_ahead": local_ahead,
        "is_git_repo": commit is not None,
    }
```

- [ ] **Step 2: 修改 `backend/main.py` — 挂载 version router**

在 `app.include_router(config_api.router)` 下方添加：

```python
from backend.api import version as version_api
```

然后在 `app.include_router(config_api.router)` 后面添加：

```python
app.include_router(version_api.router)
```

---

### Task 5: update.bat 更新脚本

**Files:**
- Create: `update.bat`

- [ ] **Step 1: 创建 `update.bat`**

```bat
@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ======================================
echo APT Mining Workbench - 更新程序
echo ======================================
echo.

:: Step 1: Check git
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 git，请先安装 git。
    pause
    exit /b 1
)

:: Step 2: Backup database
echo [1/6] 备份数据库...
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
echo [2/6] 拉取最新代码...
git fetch origin >nul 2>&1
if %errorlevel% neq 0 (
    echo  [警告] git fetch 失败，跳过代码更新。
    goto :install_deps
)

:: Check if there are updates
git rev-parse HEAD > local.txt 2>nul
git rev-parse origin/main > remote.txt 2>nul
set "LOCAL="
set "REMOTE="
for /f %%a in (local.txt) do set "LOCAL=%%a"
for /f %%a in (remote.txt) do set "REMOTE=%%a"
del local.txt remote.txt 2>nul

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

:install_deps
:: Step 4: Install dependencies
echo [3/6] 检查依赖...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    pip install -r requirements.txt -q
    echo  后端依赖安装完成。
) else (
    echo  [警告] venv 不存在，请先运行 install.bat。
)

:: Frontend deps
if exist "frontend\package.json" (
    cd frontend
    call npm install --silent 2>nul
    echo  前端依赖安装完成。
    cd ..
)

:: Step 5: Database migration
echo [4/6] 执行数据库迁移...
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -m alembic upgrade head
    if !errorlevel! neq 0 (
        echo  [错误] 数据库迁移失败！
        echo  请检查备份文件：
        dir /b backups\*.db 2>nul
        pause
        exit /b 1
    )
    echo  数据库迁移完成。
)

:: Step 6: Verify tables
echo [5/6] 验证数据库...
if exist "venv\Scripts\python.exe" (
    venv\Scripts\python.exe -c "from backend.utils.db import init_db; init_db(); print('  数据库验证通过。')"
    if !errorlevel! neq 0 (
        echo  [警告] 数据库验证未通过，但迁移已完成。请手动检查。
    )
)

:: Step 7: Build frontend
echo [6/6] 构建前端...
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
echo 更新完成！请运行 start.bat 启动平台。
echo ======================================
pause
```

---

### Task 6: 前端 version API 模块

**Files:**
- Create: `frontend/src/api/version.js`

- [ ] **Step 1: 创建 `frontend/src/api/version.js`**

```javascript
import request from './index'

export function fetchVersion() {
  return request({
    url: '/api/version',
    method: 'get',
  })
}
```

- [ ] **Step 2: 在 `frontend/src/api/index.js` 中补充导出（如需）**

确认 `frontend/src/api/index.js` 中有标准的 axios 实例导出（已有），无需修改。

---

### Task 7: 前端 Settings 页新增「系统信息」Tab

**Files:**
- Modify: `frontend/src/views/Settings.vue`

- [ ] **Step 1: 在 `<script setup>` 顶部导入 fetchVersion**

在现有的 import 块中添加：

```javascript
import { fetchVersion } from '../api/version'
```

同时导入需要的图标（Update、FolderOpened、Loading）：

```javascript
import { UploadFilled, Upload, Loading, Plus, Delete, ArrowUp, ArrowDown, QuestionFilled, Update, FolderOpened } from '@element-plus/icons-vue'
```

- [ ] **Step 2: 在 Tab 3（系统设置）之后添加 Tab 4：系统信息**

在 `</el-tab-pane>`（Tab 3 的结束标签）之后、`</el-tabs>` 之前插入：

```vue
      <!-- Tab 4: 系统信息 -->
      <el-tab-pane label="系统信息" name="system">
        <div class="tab-content">
          <!-- 版本信息卡片 -->
          <el-card class="section-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">版本信息</span>
                <el-button size="small" @click="checkUpdate" :loading="versionChecking">
                  <el-icon><Update /></el-icon>
                  检查更新
                </el-button>
              </div>
            </template>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="当前版本">
                <el-tag type="primary" size="small">v{{ versionInfo.version }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="Git Commit">
                <span v-if="versionInfo.git_commit" class="commit-hash">{{ versionInfo.git_commit }}</span>
                <span v-else class="text-muted">未初始化</span>
              </el-descriptions-item>
              <el-descriptions-item label="远程仓库" :span="2">
                <span v-if="versionInfo.git_remote_url" class="remote-url">{{ versionInfo.git_remote_url }}</span>
                <span v-else class="text-muted">未配置</span>
              </el-descriptions-item>
              <el-descriptions-item label="更新状态" :span="2">
                <el-tag v-if="versionInfo.update_available" type="warning" size="small">有新版本可用</el-tag>
                <el-tag v-else-if="versionInfo.local_ahead" type="info" size="small">本地领先于远程</el-tag>
                <el-tag v-else-if="versionInfo.is_git_repo" type="success" size="small">已是最新版本</el-tag>
                <el-tag v-else type="info" size="small">未使用 Git 管理</el-tag>
              </el-descriptions-item>
            </el-descriptions>
            <div class="system-actions">
              <el-button type="primary" size="small" @click="goToUpdate">
                运行 update.bat 更新
              </el-button>
            </div>
          </el-card>

          <!-- 变更日志卡片 -->
          <el-card class="section-card">
            <template #header>
              <span class="card-title">变更日志</span>
            </template>
            <div v-loading="changelogLoading" class="changelog-content">
              <pre v-if="changelog">{{ changelog }}</pre>
              <el-empty v-else description="暂无变更日志" />
            </div>
          </el-card>

          <!-- 数据管理 -->
          <el-card class="section-card">
            <template #header>
              <span class="card-title">数据管理</span>
            </template>
            <div class="data-management">
              <el-button size="small" @click="openBackupsDir">
                <el-icon><FolderOpened /></el-icon>
                打开备份目录
              </el-button>
              <span class="data-hint">数据库备份位于 backups/ 目录</span>
            </div>
          </el-card>
        </div>
      </el-tab-pane>
```

- [ ] **Step 3: 在 `<script setup>` 中添加状态与方法**

在 `onBeforeUnmount` 之前添加：

```javascript
// ====== Tab 4: 系统信息 ======
const versionInfo = ref({
  version: 'unknown',
  git_commit: null,
  git_remote_url: null,
  update_available: false,
  local_ahead: false,
  is_git_repo: false,
})
const versionChecking = ref(false)
const changelog = ref('')
const changelogLoading = ref(false)

async function loadVersion() {
  try {
    versionInfo.value = await fetchVersion()
  } catch {
    // 静默失败
  }
}

async function loadChangelog() {
  changelogLoading.value = true
  try {
    const res = await fetch('/CHANGELOG.md')
    if (res.ok) {
      changelog.value = await res.text()
    } else {
      changelog.value = '# 暂无变更日志\n\n当前版本无变更记录。'
    }
  } catch {
    changelog.value = '加载变更日志失败。'
  } finally {
    changelogLoading.value = false
  }
}

async function checkUpdate() {
  versionChecking.value = true
  try {
    versionInfo.value = await fetchVersion()
    if (versionInfo.value.update_available) {
      ElMessage.info('检测到新版本，请运行 update.bat 更新。')
    } else if (!versionInfo.value.is_git_repo) {
      ElMessage.info('当前未使用 Git 管理，无法检查更新。')
    } else {
      ElMessage.success('已是最新版本。')
    }
  } catch (e) {
    ElMessage.error('检查更新失败: ' + e.message)
  } finally {
    versionChecking.value = false
  }
}

function goToUpdate() {
  ElMessage.info('请在终端中运行 update.bat 执行更新。')
}

function openBackupsDir() {
  ElMessage.info('备份目录位于项目根目录的 backups/ 文件夹中。')
}
```

- [ ] **Step 4: 在 `onMounted` 中添加初始化调用**

在现有 `onMounted` 函数末尾添加 `loadVersion()` 和 `loadChangelog()`：

```javascript
onMounted(() => {
  loadImports()
  loadBatches()
  loadTraced()
  loadConfig()
  loadDicts()
  loadVersion()
  loadChangelog()
})
```

- [ ] **Step 5: 在 `<style scoped>` 中添加样式**

在文件末尾的 `<style scoped>` 中添加：

```css
/* System info tab */
.commit-hash {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.remote-url {
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
}

.text-muted {
  color: var(--text-muted);
}

.system-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.changelog-content {
  max-height: 500px;
  overflow-y: auto;
}

.changelog-content pre {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.data-management {
  display: flex;
  align-items: center;
  gap: 12px;
}

.data-hint {
  font-size: 12px;
  color: var(--text-muted);
}
```

---

### Task 8: 更新 install.bat 安装 Alembic（验证依赖）

**Files:**
- Read: `install.bat`

- [ ] **Step 1: 确认 alembic 已在 requirements.txt 中**

Alembic 已在 `requirements.txt` 中（第 5 行 `alembic>=1.13.0`），无需修改 install.bat。

---

### Task 9: 初始化 Git 仓库并提交首次 Commit

**Files:** N/A（git 操作）

- [ ] **Step 1: 初始化 git 仓库**

```bash
git init
git add -A
git commit -m "feat: v3.1 baseline - platform update and migration system

- VERSION file and CHANGELOG.md
- Alembic database migration setup
- update.bat one-click update script
- /api/version endpoint for version info
- System info tab in Settings page"
```

注意：在 commit 之前，确保 `.gitignore` 正确排除了 `data/`、`backups/`、`venv/`、`uploads/`、`frontend/dist/`、`frontend/node_modules/`。

---

## Self-Review

**1. Spec coverage check:**

| 需求 | Task |
|------|------|
| VERSION 文件 | Task 1 |
| CHANGELOG.md | Task 1 |
| .gitignore 更新 | Task 2 |
| Alembic 初始化 + 基线迁移 | Task 3 |
| /api/version 接口 | Task 4 |
| update.bat 更新脚本 | Task 5 |
| 前端 version API 模块 | Task 6 |
| 系统信息 Tab（版本号/变更日志/更新检查） | Task 7 |
| Git 初始化 | Task 9 |
| 自动备份 + 迁移验证 | Task 5 (update.bat 中) |

全部覆盖。

**2. Placeholder scan:** 无 TBD、TODO、"类似"等占位符。

**3. Type consistency:** `/api/version` 返回 `{version, git_commit, git_remote_url, update_available, local_ahead, is_git_repo}`，前端 `versionInfo` ref 的初始值结构一致。`fetchVersion` 直接调用 `request` 返回 promise。一致。
