# Changelog

## v4.14 - 2026-05-25

### 修复：创建事件后 IOC 不显示事件标签

**根因：** 事件匹配存在两个问题：(1) 大小写不一致 — Excel 导入的 target（如 `MASKED_DOMAIN.COM`）与用户创建事件时输入的 target（如 `masked_domain.com`）大小写不同，JOIN 匹配失败；(2) 端口空值不匹配 — 创建事件时 IOC 端口为空，但告警端口有值（如 `53`），`'' != '53'` 导致 JOIN 失败。

### 后端

- 修复：`candidate_repo.go` events CTE JOIN — `UPPER(e.target) = UPPER(a.target)` 大小写归一化 + `e.port IN ('', '*')` 空端口通配
- 修复：`candidate_repo.go` traced CTE JOIN — `UPPER(tr.target) = UPPER(a.target)` 大小写归一化 + `tr.port IN ('', ...)` 空端口通配
- 修复：`candidate_repo.go` HideTraced WHERE — `UPPER(tt.target) = UPPER(a.target)` 大小写归一化
- 修复：`candidate_repo.go` HideClosed WHERE — `UPPER(mei.target) = UPPER(a.target)` 大小写归一化
- 修复：`event_repo.go` CreateEventTx / AddIOCs — 插入 IOC 时 `strings.ToLower(target)` 存储归一化

---

## v4.12 - 2026-05-25

### 修复：事件恢复活跃时色板颜色不同步

**根因：** `EventManager.vue` 关闭事件时色板变蓝（`#409EFF`），但恢复活跃时只更新数据库颜色为红（`#FF5722`），未同步更新 `editColor.value`，导致色板仍显示蓝色。

### 前端

- 修复：`EventManager.vue` 恢复活跃时色板同步变为红色 `#FF5722`

---

## v4.11 - 2026-05-25

### 修复：事件提交 IOC 格式不兼容

**根因：** `event_handler.go` 定义 `IOCs []string` 期望 `["target:port"]` 字符串数组，但前端 EventManager 发送 `[{target, port}]` 对象数组，Go 反序列化失败。

### 后端

- 修复：`event_handler.go` CreateEvent / AddIOCs — `IOCs []string` → `IOCs []repository.IOC`，移除字符串拆分逻辑

### 前端

- 修复：`Workbench.vue` eventForm.iocs 初始化从字符串改为对象，submitEvent 直接透传

---

## v4.10 - 2026-05-24

### 对齐 3.2.10 功能修复（第2批）

### 后端

- 修复：`import_service.go` processImport — 每行写入 `import_rows` 表（parsed/skipped_duplicate/failed），修复导入详情页行明细始终为空
- 修复：`import_service.go` GetImportRows — 补全 `SELECT ir.* FROM import_rows ir` 前缀，修复 SQL 语法错误
- 修复：`candidate_repo.go` 关键词搜索 — 从 `to_tsvector('simple')` GIN 全文搜索改为 `ILIKE '%keyword%'` 跨 6 字段模糊匹配，支持中文子串搜索
- 修复：`candidate_repo.go` HideTraced — 从精确匹配改为 `COALESCE(tt.port, '') IN ('', COALESCE(a.port, ''))`，追踪记录端口为空时匹配所有告警端口
- 新增：`model.go` 辅助字段 — `target_kind_label`、`trace_status_label`、`device_note_summary`、`heat_summary`
- 修复：`import_service.go` ListImports — 改为强类型 `sql.NullTime` 扫描 + `YYYY-MM-DD HH:MM:SS` 格式化
- 修复：`import_service.go` content_hash — 从 32-bit 滚动哈希改为 `crypto/sha256`，降低碰撞风险
- 新增：`ioc_extractor.go` — `network:/domain:/dns:` 前缀剥离、可执行文件扩展名过滤、URL hostname 去重、中文字符支持增强

### 验收

- 10/10 场景 + 15 单元测试通过

---

## v4.9 - 2026-05-24

### 对齐 3.2.10 核心行为修复（第1批）

### 后端

- 修复：`candidate_repo.go` 候选去重 — `ROW_NUMBER() OVER (PARTITION BY device_id, target, COALESCE(port,'') ORDER BY ...)` 去重
- 新增：`event_repo.go` CreateEventTx — 插入 `event_followups` 记录"创建事件: {event_name}"；查找或创建 `"事件挖掘: {event_name}"` 永久标签；为每个设备插入 `device_tags` 记录
- 新增：`event_repo.go` UpdateEvent — status 变更自动插入 `action_type='status_change'` 跟进记录
- 修复：`import_service.go` DeleteImport — 级联删除 alerts → import_rows → import_sheets → imports
- 修复：`event_repo.go` UpdateEvent — 改为只更新非空字段，前端只传 status 时不会清空 name/color/note
- 修复：`db.go` 连接字符串 — 改为 URL 格式 `postgres://user:pass@host:port/dbname`，修复空密码时连接到默认库的 bug

---

## v4.8 - 2026-05-23

### 对齐 3.2.10 功能修复

### 后端

- 新增：`candidate_repo.go` 评分 — 追踪减分项：活跃追踪 -12 分、过期追踪 -4 分；traced CTE 基于 `trace_ttl_days` 动态计算 active/expired 状态
- 新增：`candidate_service.go` Badge — 从 5 种补全到 9 种：`advanced_crime`（高级黑灰产）、`cross_day`（跨天持续）、`lateral`（横向扩散）、`expired_revive`（追踪过期）；修复 `apt_dict` 使用 APT 词典精确匹配、`noise_family` 使用噪声词典
- 新增：`candidate_service.go` badges_filter — 放大查询 page_size 10 倍，Go 层按 badge name/label 过滤后分页返回
- 新增：`candidate_repo.go` GetFilterOptions — 补全 `priority`、`badges`、`ioc_note` 三个缺失键
- 新增：`tag_handler.go` ImportTextFiles — 文件名→标签预设匹配："01排查成功"→排查成功(绿)、"02重点设备"→重点设备(红)、"03不好查"→不好查(灰)

### 验收

- 15 项回归测试全部通过

---

## 配置统一 - 2026-05-24

### 运维

- 新增：根目录 `.env` 统一数据库和端口配置（`APT_DB_HOST/PORT/USER/PASSWORD/NAME`、`APT_SERVER_PORT=9099`）
- 删除：旧 PROD/TEST 双变量体系（`APT_DB_USER_PROD`、`APT_DB_NAME_TEST` 等 6 个变量）
- 修复：`start.py` / `dev.py` / `stop.py` 端口默认从 `.env` 读取
- 修复：`frontend/vite.config.js` / `App.vue` 默认端口改为 9099
- 修复：`config/config.yaml` 端口改为 9099

---

## v4.7.6 - 2026-05-22

### 修复：启动脚本防旧版本

**根因：** `start.py` 仅在 exe 不存在时构建，源码更新后直接运行会跳过编译跑旧 exe。

### 后端

- 新增：`start.py` `needs_rebuild()` — 递归检查 `.go` 文件 mtime 是否比 exe 新，自动触发重新构建；新增 `--no-rebuild` 参数
- 新增：`dev.py` — 开发模式启动脚本，用 `go run main.go` 直接跑最新代码，支持 `--test` / `--no-browser` / `--host` / `--port`

---

## v4.7.5 - 2026-05-22

### 修复：日期筛选后 loading 卡死

**根因：** `Workbench.vue` `displayData` computed 内部修改 `total.value`，产生 Vue 响应式级联更新循环，阻塞 UI 主线程。

### 前端

- 修复：`Workbench.vue` `total.value` 赋值从 `displayData` 移至 `displayTotal` computed，消除响应式副作用

---

## v4.7.4 - 2026-05-22

### 滚动条加宽

### 前端

- 修复：`global.css` `::-webkit-scrollbar` 从 14px 改为 28px

---

## v4.7.3 - 2026-05-22

### 修复：日期范围筛选结果不符

**根因：** `candidate_repo.go` `date_end` 使用 `<= $N`，PostgreSQL 将 `'2026-05-15'` 解析为 `'2026-05-15 00:00:00'`，结束日期全天数据被截断。

### 后端

- 修复：`candidate_repo.go` date_end 改为 `a.first_alert_time < ($N::date + interval '1 day')`

---

## v4.7.2 - 2026-05-22

### 分页容量提升 + 滚动条加宽

### 前端

- 修复：`Workbench.vue` 默认 `pageSize` 从 50 改为 1000；`page-sizes` 改为 `[1000, 2000, 5000]`
- 修复：`Workbench.vue` 分页器按钮宽度加至 96px，选择器宽度 120px
- 修复：`global.css` `::-webkit-scrollbar` 从 10px 改为 14px

---

## v4.7.1 - 2026-05-22

### 修复：device_id_count 排序报错

**根因：** `candidate_repo.go` `scored` CTE 中 `device_id_count` 仅在 `json_build_object` 中作为键名存在，不是 CTE 的真实输出列，`ORDER BY` 引用时 PostgreSQL 报 42703 错误。

### 后端

- 修复：`candidate_repo.go` scored CTE 新增 `COALESCE(dh.device_alert_count, 1) AS device_id_count` 输出列

---

## v4.7 - 2026-05-22

### 修复：设备ID计数不显示 + 静态文件同步

**根因：** Go 后端从 `backend_v2/static/` 提供静态文件，不是 `frontend/dist/`。`static/` 中是旧构建产物，不含 `device_id_count` 字段。

### 后端

- 修复：将 `frontend/dist/*` 同步到 `backend_v2/static/`
- 新增：`install.py` `sync_static()` 步骤，构建前端后自动同步静态文件

---

## v4.6 - 2026-05-22

### 全链路回归测试

### 验收

- 11 项核心功能回归测试通过（基于 apt_mining_test 测试库 12552 条数据）：创建标签+批量打标、IOC 备注、事件 CRUD+IOC+设备+跟进、事件关闭/激活、编辑 IOC 备注、编辑事件、删除设备标签、批次软删除/恢复、hide_closed 端口通配、设备标签筛选 API、表头排序

---

## v4.1 - 2026-05-22

### Go 平台打磨

### 后端

- 修复：逐项对照 v3.x Python 版 82 个阶段优化项，确认 Go 版已实现 10/11 项
- 修复：`candidate_repo.go` hide_closed 端口通配 — 原用精确匹配，改为 `(COALESCE(mei.port, '') = COALESCE(a.port, '') OR mei.port = '*')` 支持通配端口

---

## v4.0.8 - 2026-05-21

### 旧 Python 后端及脚本全部删除

### 清理

- 删除：`backend/` 目录（~50 文件）、`requirements.txt`、全部 Python 运维脚本（start/stop/install/upgrade/pack/push 等）
- 删除：`migrate_old_to_prod.py`/`migrate_sqlite_to_pg.py`/`migrate_test_to_prod.py`、`export_ops_data.py`/`generate_demo_data.py`/`recover_import.py`、`__pycache__/`、`venv/`
- 保留：Go 启动脚本（`go_import_and_start.bat`/`init_db.bat`/`startGo*.bat`/`stopGo*.bat`）

---

## v4.0.7 - 2026-05-21

### bat 脚本修复 + import_ops_data.py 重写

### 运维

- 修复：`startGo.bat`/`startGoTest.bat`/`go_import_and_start.bat` 从 `python start.py --go` 改为 `cd backend_v2 && apt-mining.exe`，直接启动编译好的 Go 可执行文件
- 修复：`init_db.bat` 末尾提示从"运行 import_ops_data.py"改为"双击 startGo.bat"
- 修复：误删的 `go_import_and_start.bat` 重建
- 修复：`import_ops_data.py` 从 psql 子进程改为 psycopg2 直连，解决 Windows GBK 编码导致中文乱码 bug
- 修复：`import_ops_data.py` 表导入顺序（tag_batches 先于 tags 满足 FK 约束）、移除不存在的 config_data 表
- 验证：apt_mining_test 测试库导入 6 条数据无 bug，API 返回中文正确

---

## v4.0.6 - 2026-05-21

### 根目录脚本全面修复

### 运维

- 修复：`start.py` 移除 uvicorn/venv 路径，改为纯 Go 后端启动器，自动设置 DB 凭据
- 修复：`install.py` 移除 venv/pip/requirements.txt，改为检查 Go+Node.js、go mod download、构建 Go 二进制、构建前端
- 修复：`upgrade.py` 后端依赖安装改为 go mod download，数据库备份改为 pg_dump（PostgreSQL）
- 验证：start.py/install.py/stop.py/upgrade.py --help 通过，install.py 全流程执行成功

---

## v4.0.5 - 2026-05-21

### 修复 Excel 上传全部失败（112,805 行）

**根因：** 表头映射不匹配 + SQL INSERT 语法错误 + 前端响应格式不一致。

### 后端

- 修复：`extractRow` 表头映射 — Excel 实际列名 `外联端口`/`APT组织`/`APT组织分类` 与 Go 期望的 `端口`/`原始APT组织`/`APT分级` 不一致，支持双名称回退
- 修复：SQL INSERT 去重 — 从 `ON CONFLICT (content_hash) DO NOTHING`（依赖不存在的唯一索引）改为 `INSERT ... SELECT ... WHERE NOT EXISTS`
- 修复：`uploads/` 目录自动创建、multipart 上传限制提升至 500MB
- 修复：`processImport` 统计 — 检查 `result.RowsAffected()`，affected=0 时计入 `totalSkipped`，修复重复行误计为成功的统计失真

### 前端

- 修复：`handleUploadExcel` 期望 `result.jobs` 数组但后端返回单个对象，兼容两种格式
- 修复：axios 错误拦截器增加 `error` 字段解析（后端返回 `{"error": "..."}` 而非 `{"detail": "..."}`）

---

## v4.0.4 - 2026-05-21

### Git 忽略 + 发布脚本 + VERSION 统一

### 运维

- 修复：`backend_v2/.gitignore` 追加 `.gocache/`，Go 编译缓存不再被 `git status` 列出
- 修复：`pack_release.py` `EXCLUDE_DIRS` 追加 `.gocache`，`push_release.py` `GIT_EXCLUDE` 追加 `.gocache/`
- 修复：统一使用根目录 `VERSION` 文件 — 删除 `backend_v2/VERSION`（旧版本 3.3.7），`health.go` 改为读取 `../VERSION` 回退到本地 `VERSION`
- 修复：`pack_release.py` `copy_ignore_func` 排除子目录中的 `VERSION`，`upgrade.py` `_merge_dir` 增加 `skip_version` 参数

---

## v4.0.3 - 2026-05-21

### 脚本可用性修复

### 运维

- 修复：`install.py`/`start.py`/`pack_release.py`/`upgrade.py` 统一将 `GOCACHE` 指向 `backend_v2/.gocache`，规避 Windows 全局 Go 缓存权限问题
- 修复：`upgrade.py` 移除过时的 `start.py --go`/`start.bat` 提示
- 修复：`startGo.bat` 增加缺失 `apt-mining.exe` 的明确引导
- 修复：`README.md` 启动说明改为先 `init_db.bat`，统一 `backend_v2` 路径与 `python start.py` 用法

---

## v4.0.1 - 2026-05-21

### 修复：研判工作台 5 个 bug

### 后端

- 新增：`GET /api/alert-candidates` 响应增加 `filter_options` 字段，重写 `GetFilterOptions()` 返回 `map[string][]string`
- 修复：`candidate_repo.go` 设备ID计数 — `heat.device_target_count` → `heat.target_device_count`
- 修复：`candidate_repo.go` 源IP计数 — SQL 增加 `source_ip_count` 输出，去除前端 `?? 1` 硬编码回退

### 前端

- 修复：`Workbench.vue` 设备ID列增加 el-popover 筛选图标和搜索功能
- 修复：`Workbench.vue` submitEvent 将 `iocs` 从对象数组改为字符串数组，匹配后端期望格式

---

## v4.0.0 - 2026-05-21

### Go 全栈重写

**为什么重写：** v3.x 累计 82 个阶段补丁后架构复杂度超过可维护上限，性能瓶颈（SQLite 单连接阻塞、快照+实时覆盖不一致、导入卡死）无法通过增量修复解决。换 Go + PostgreSQL 强制从头设计，切断补丁惯性。

### 后端

- 新增：Go 1.22 + Gin 项目结构，handler / service / repository / model 四层架构
- 新增：PostgreSQL 替代 SQLite，14 张表 + GIN 全文搜索索引 + 候选部分索引
- 新增：候选查询 CTE SQL（1 条 SQL 搞定评分/Badge/热度聚合），替代 v3.x 14 次 SQL + Python 装饰
- 新增：Excel 流式导入（goroutine 后台顺序处理，每 500 行 batch commit），不阻塞查询
- 新增：事件 CRUD + IOC 自动提取 + 设备关联
- 新增：标签批次管理 + TXT 批量打标 + 设备标签
- 新增：IOC 追踪管理
- 新增：配置读写 + 词典加载
- 新增：健康检查 + 版本信息接口
- 删除：snapshot_builder.py（1246 行）、快照查询路径、候选缓存管理、patch_snapshot_for_* 增量刷新
- 删除：SQLite StaticPool、QueuePool、WAL checkpoint 等兼容代码

### 前端

- 新增：5 个页面对接 Go 后端（Workbench / EventManager / AlertList / Settings / IocNotes）
- 新增：列配置文件化（columns.json）
- 保留：三主题切换（暗色/VSCode 浅色/VS2026 蓝色）
- 保留：表头筛选、列宽拖拽、排序按钮
- 保留：Excel 风格上传、导入详情、失败行下载

### 运维

- 新增：`startGo.bat` / `stopGo.bat` 正式实例（8088）
- 新增：`startGoTest.bat` / `stopGoTest.bat` 测试实例（9099）
- 新增：`init_db.bat` PostgreSQL 初始化
- 新增：`go_import_and_start.bat` Go 依赖导入+启动一键完成
- 删除：全部 Python 运维脚本（start.py / stop.py / install.py / upgrade.py / pack_release.py / push_release.py）

---

## v3.3.x（Python/FastAPI 旧版，已停止维护）

历史变更记录已归档。v3.x 共经历 82 个迭代阶段（阶段0~82），涵盖前端重建、性能优化、快照表方案、导入体验改进等工作。详见 git 历史。
