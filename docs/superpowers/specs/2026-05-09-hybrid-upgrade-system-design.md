# 混合模式一键升级系统 — 设计文档

> 日期: 2026-05-09
> 版本: v3.1 → v3.1.x
> 状态: 待实现

---

## 背景

APT 挖掘工作台迭代速度快（AI 开发环境），正式环境部署在另一台机器上，由其他同事操作，含敏感数据。需要一套机制让正式环境能安全地同步到最新代码，同时绝不影响数据。

正式环境可能联网（可 git pull）也可能离线（需离线包）。

## 核心原则

1. **数据零风险** — `data/`、`uploads/`、`backups/` 在任何操作中都不被删除、覆盖、移动
2. **操作极简** — 同事只需"双击 .bat"，不需要理解 git 或命令行
3. **双通道分发** — 联网走 git pull，离线走 zip 包，正式侧自动检测
4. **升级前自动备份** — 每次升级前备份 DB 到 backups/

## 文件清单

### 新增

| 文件 | 位置 | 作用 |
|------|------|------|
| `一键打包.bat` | 开发侧 | 递增版本号 + npm build + 打 zip 发布包 |
| `一键上传.bat` | 开发侧 | git add + commit + push + tag |
| `upgrade.bat` | 正式侧（随代码分发） | 唯一操作入口：自动检测 git/zip → 升级 |

### 删除

| 文件 | 原因 |
|------|------|
| `start-hide.bat` | 取消 |
| `update.bat` | 功能合并到 `upgrade.bat` |

### 不改

| 文件 | 说明 |
|------|------|
| `start.bat` | 保持现状 |
| `install.bat` | 仍用于首次安装 |
| `VERSION` | 单行版本号，不改格式 |
| `CHANGELOG.md` | 变更日志，不改格式 |

### 修改

| 文件 | 修改 |
|------|------|
| `.gitignore` | 添加 `releases/` 目录排除 |

---

## 一、开发侧：`一键打包.bat`

### 流程

```
1. chcp 65001 (UTF-8)
2. 读取 VERSION (如 3.1.2)，显示当前版本
3. 提示输入新版本号（回车默认 +0.0.1 → 3.1.3）
4. 更新 VERSION 文件
5. 检测 frontend/package.json 是否存在
6. cd frontend && npm run build && cd ..
7. 创建 releases/ 目录（如不存在）
8. 打 zip → releases/apt-mining-v{版本号}.zip
   排除列表：
   - data/
   - uploads/*（保留 uploads/.keep）
   - backups/
   - venv/
   - frontend/node_modules/
   - .git/
   - .claude/
   - __pycache__/
   - *.pyc
   - tmp_*.db
   - *_regression.db
   - releases/
9. 显示 zip 路径和大小
```

### 输出示例

```
======================================
APT Mining Workbench - 一键打包
======================================
当前版本: 3.1.2
请输入新版本号 [3.1.3]:
[1/3] 更新版本号... 3.1.3
[2/3] 构建前端... 完成
[3/3] 打包发布... 完成

发布包: releases\apt-mining-v3.1.3.zip
请将此文件发送给正式环境。
======================================
```

### 打包方式

使用 PowerShell `Compress-Archive` 或 7z。
由于 `Compress-Archive` 不支持排除模式，实际方案：
1. `robocopy` 到临时目录 `_release_tmp/`，带 /XD /XF 排除
2. PowerShell `Compress-Archive` 压缩临时目录
3. 删除临时目录

---

## 二、开发侧：`一键上传.bat`

### 流程

```
1. chcp 65001 (UTF-8)
2. 检测 git 是否可用
3. git status 显示变更文件摘要
4. 如果没有变更，提示"没有需要提交的变更"并退出
5. 提示输入提交说明
6. git add -A
7. git commit -m "提交说明"
8. git push origin main
   - 如果 push 失败，提示检查网络/远程仓库
9. 读取 VERSION，执行 git tag v{版本号}
   - 如果 tag 已存在，跳过
10. git push --tags
11. 显示完成信息
```

### 输出示例

```
======================================
APT Mining Workbench - 一键上传
======================================
变更文件:
  M backend/api/alerts.py
  M frontend/src/views/Workbench.vue
  A backend/api/new_feature.py

请输入提交说明: 修复表头排序bug

[1/3] 提交代码... 完成
[2/3] 推送到远程... 完成
[3/3] 创建标签 v3.1.3... 完成

代码已推送，正式环境可执行 upgrade.bat 拉取。
======================================
```

---

## 三、正式侧：`upgrade.bat`

### 流程

```
1. chcp 65001 (UTF-8)
2. 读取并显示当前 VERSION（如文件不存在，显示"未知"）
3. 备份数据库
   - 检查 data\workbench.db 是否存在
   - 存在 → 创建 backups/ 目录 → copy 到 backups/workbench_YYYYMMDD_HHMMSS.db
   - 不存在 → 跳过
4. 检测升级源（按优先级）：
   a. 检测当前目录下是否有 apt-mining-v*.zip 文件
      - 有 → ZIP 模式（优先，因为用户主动放了包就说明要用离线方式）
      - 找到多个 → 取文件名版本号最大的那个
   b. 没有 zip → 检测 git 是否可用且有 remote
      - where git 成功 + git remote 有输出 → GIT 模式
      - git fetch 成功 → 比较 HEAD vs origin/main
        - 相同 → 提示已是最新
        - 不同 → git pull origin main
      - git fetch 失败 → 提示网络错误
   c. 既没有 zip 也没有 git → 提示用户放置 zip 或配置 git
5. [ZIP 模式] 安全解压：
   - 解压到 _upgrade_tmp/
   - robocopy _upgrade_tmp/ ./ /E /IS /IT
     /XD data uploads backups venv node_modules .git .claude _upgrade_tmp releases
   - 删除 _upgrade_tmp/
6. 安装后端依赖
   - venv 存在 → call venv\Scripts\activate.bat → pip install -r requirements.txt -q
   - venv 不存在 → 提示运行 install.bat
7. 安装前端依赖 + 构建
   - cd frontend → npm install --silent → npm run build → cd ..
8. 读取新 VERSION，显示升级结果（旧版本 → 新版本）
9. [ZIP 模式] 升级完成后，将已使用的 zip 移到 releases/ 归档
10. 提示运行 start.bat
```

### 输出示例（ZIP 模式）

```
======================================
APT Mining Workbench - 一键升级
======================================
当前版本: 3.1.2

[1/5] 备份数据库... 已备份: backups\workbench_20260509_143022.db
[2/5] 检测升级方式... 离线包模式
      找到升级包: apt-mining-v3.1.3.zip
      正在解压覆盖代码...（数据目录已保护）
      代码更新完成。
[3/5] 安装后端依赖... 完成
[4/5] 构建前端... 完成
[5/5] 版本确认... 3.1.2 → 3.1.3

======================================
升级完成！请运行 start.bat 启动平台。
如需回滚，备份文件: backups\workbench_20260509_143022.db
======================================
```

### 输出示例（GIT 模式）

```
======================================
APT Mining Workbench - 一键升级
======================================
当前版本: 3.1.2

[1/5] 备份数据库... 已备份: backups\workbench_20260509_143022.db
[2/5] 检测升级方式... Git 模式
      检测到新版本，正在拉取...
      代码更新完成。
[3/5] 安装后端依赖... 完成
[4/5] 构建前端... 完成
[5/5] 版本确认... 3.1.2 → 3.1.3

======================================
升级完成！请运行 start.bat 启动平台。
如需回滚，备份文件: backups\workbench_20260509_143022.db
======================================
```

---

## 四、ZIP 解压安全策略

核心风险：zip 直接解压可能覆盖正式数据。

解决方案：两阶段解压

```
阶段1: Expand-Archive → _upgrade_tmp/ （临时目录）
阶段2: robocopy _upgrade_tmp/ ./ /E /IS /IT
        /XD data uploads backups venv node_modules .git .claude _upgrade_tmp releases
阶段3: rmdir /S /Q _upgrade_tmp
```

robocopy 的 /XD 参数确保受保护目录永远不被覆盖，即使 zip 里包含了这些目录。

---

## 五、数据库兼容性

**策略：继续依赖 `_ensure_runtime_schema()` 做向前兼容。**

- Excel 源数据格式不变，DB schema 基本稳定
- `_ensure_runtime_schema()` 在 `start.bat` 启动时自动执行，补充新字段和索引
- Alembic 作为保底工具保留，但不在升级流程中强制执行
- 升级脚本不触碰数据库，所有 schema 变更由应用启动时处理

---

## 六、回滚策略

### 代码回滚

- **Git 模式**：在正式机上 `git checkout v3.1.2`
- **ZIP 模式**：用上一个版本的 zip 重新运行 `upgrade.bat`

### 数据回滚

- 停止平台
- 复制 `backups/workbench_YYYYMMDD_HHMMSS.db` → `data/workbench.db`
- 启动平台

### 备份保留策略

不自动清理备份。磁盘不够时用户手动删除旧备份。

---

## 七、.gitignore 修改

新增一行：

```
releases/
```

---

## 八、同事操作手册

### 联网环境（已配好 git）

> 双击 `upgrade.bat`，等它跑完，再双击 `start.bat`。

### 离线环境

> 1. 把收到的 `apt-mining-v3.x.x.zip` 放到平台根目录
> 2. 双击 `upgrade.bat`，等它跑完，再双击 `start.bat`
