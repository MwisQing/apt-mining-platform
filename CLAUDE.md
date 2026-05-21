# APT Mining Workbench v4.0 — AI 协作上下文

> **本文件是 AI 助手的上下文入口。每次新对话开始时，AI 必须先读取本文件。**
> **每完成一个阶段后，AI 必须更新底部的"进度记录"部分。**

---

## 项目概述

APT 挖掘工作台：安全分析师从海量网络告警中挖掘 APT 事件的单机离线平台。

**技术栈：** Go 1.22 + Gin + PostgreSQL（后端） / Vue 3 + Vite + Element Plus（前端）
**运行方式：** 本地启动，浏览器访问 `http://127.0.0.1:8088`
**版本：** v4.0（Go 全栈重写，详见 `docs/superpowers/specs/2026-05-18-apt-mining-go-rewrite-design.md`）

---

## 用户工作流

```
1. 收到告警 Excel（10w 条）→ 上传导入平台
2. 导入设备标签 TXT（01排查成功/02重点设备/03不好查）→ 批量打标
3. 打开研判工作台 → 看候选结果（已自动筛apt/远控、评分、排序）
4. 逐条研判：
   - 有价值 → 创建事件（关联IOC+端口），事件按IOC匹配自动命中
   - 已知的 → 标记追踪过
   - 设备排查完 → 更新设备标签
5. 下次导入新数据，之前的标签和追踪自动生效
```

> **事件匹配规则：** 事件仅通过 IOC+端口 匹配告警行，不再通过设备ID匹配。设备标签仍按设备ID独立展示。

---

## 项目目录结构

```
apt-mining-platform/
├── backend_v2/                 # Go 后端（v4.0，当前主力）
│   ├── main.go                   # 入口：Gin 路由 + PostgreSQL + 静态文件
│   ├── go.mod / go.sum
│   ├── internal/
│   │   ├── handler/              # HTTP 请求处理
│   │   │   ├── candidate_handler.go   # /api/alert-candidates
│   │   │   ├── health.go              # /api/health, /api/version
│   │   │   ├── import_handler.go      # /api/imports
│   │   │   ├── event_handler.go       # /api/events
│   │   │   ├── tag_handler.go         # /api/tags
│   │   │   ├── traced_handler.go      # /api/traced
│   │   │   ├── config_handler.go      # /api/config
│   │   │   ├── device_handler.go      # /api/devices
│   │   │   └── snapshot_handler.go    # /api/snapshots
│   │   ├── service/              # 业务逻辑
│   │   │   ├── candidate_service.go   # 候选 CTE SQL 构建
│   │   │   ├── import_service.go      # Excel 流式读取 + 后台队列
│   │   │   ├── ioc_extractor.go       # IOC 自动提取
│   │   │   └── badge_engine.go        # Badge 规则引擎
│   │   ├── repository/           # 数据库操作
│   │   │   ├── candidate_repo.go
│   │   │   ├── event_repo.go
│   │   │   ├── tag_repo.go
│   │   │   ├── traced_repo.go
│   │   │   └── device_repo.go
│   │   ├── model/model.go        # 数据结构体
│   │   └── config/config.go      # YAML 配置加载
│   └── migrations/               # PostgreSQL 迁移 SQL
├── frontend/src/                 # Vue 3 源码
│   ├── views/
│   │   ├── Workbench.vue         # 研判工作台
│   │   ├── EventManager.vue      # 事件管理
│   │   ├── AlertList.vue         # 原始告警列表
│   │   ├── IocNotes.vue          # IOC 备注管理
│   │   └── Settings.vue          # 导入与设置
│   ├── api/                      # HTTP 请求封装
│   ├── composables/              # 可复用逻辑
│   └── router/index.js           # 路由配置
├── frontend/dist/                # 前端构建产物
├── frontend/public/columns.json  # 列配置文件（可提交）
├── config/                       # YAML 配置 + 词典
│   ├── config.yaml
│   ├── apt_org_dict.yaml
│   ├── advanced_crime.yaml
│   └── noise_family.yaml
├── data/                         # PostgreSQL 数据目录
├── uploads/                      # 上传文件暂存
├── docs/superpowers/
│   ├── specs/                    # 设计文档
│   │   └── 2026-05-18-apt-mining-go-rewrite-design.md
│   └── plans/                    # 实施计划（4 个阶段）
│       ├── 2026-05-18-apt-mining-go-rewrite-plan-1-foundation.md
│       ├── 2026-05-18-apt-mining-go-rewrite-plan-2-core-engine.md
│       ├── 2026-05-18-apt-mining-go-rewrite-plan-3-business-apis.md
│       └── 2026-05-18-apt-mining-go-rewrite-plan-4-frontend-migration.md
├── CLAUDE.md                     # ← 本文件
├── VERSION
├── CHANGELOG.md
├── start.py / stop.py            # 运维脚本
└── init_db.bat                   # PostgreSQL 初始化
```

---

## 后端 API 清单

所有端点路径与 v3.x Python 版保持一致，仅后端实现从 Python 改为 Go。

### 核心接口

| 方法 | 路径 | Go Handler | 说明 |
| ---- | ---- | ---------- | ---- |
| GET | `/api/health` | health.go | 健康检查 |
| GET | `/api/version` | health.go | 版本信息 |
| GET | `/api/alert-candidates` | candidate_handler.go | **候选结果**（核心，CTE SQL 评分） |
| GET | `/api/alerts` | candidate_handler.go | 告警列表 |
| GET | `/api/alerts/options` | candidate_handler.go | 筛选选项 |
| POST | `/api/alerts/export` | candidate_handler.go | 导出 xlsx |
| GET | `/api/events` | event_handler.go | 事件列表 |
| POST | `/api/events` | event_handler.go | 创建事件 |
| GET/PATCH/DELETE | `/api/events/{id}` | event_handler.go | 事件 CRUD |
| POST | `/api/events/{id}/followups` | event_handler.go | 添加跟进 |
| POST/DELETE | `/api/events/{id}/devices` | event_handler.go | 关联/移除设备 |
| POST/DELETE | `/api/events/{id}/iocs` | event_handler.go | 关联/移除 IOC |
| GET | `/api/tags` | tag_handler.go | 标签列表 |
| GET/POST/DELETE | `/api/tags/batches` | tag_handler.go | 标签批次 |
| POST | `/api/tags/batches/import-text-files` | tag_handler.go | TXT 批量打标 |
| GET/POST/DELETE | `/api/tags/devices/...` | tag_handler.go | 设备标签 |
| GET/POST/PATCH/DELETE | `/api/traced` | traced_handler.go | IOC 追踪 |
| POST | `/api/imports` | import_handler.go | 上传 Excel（goroutine 后台处理） |
| GET/DELETE | `/api/imports/...` | import_handler.go | 导入管理 |
| GET/POST | `/api/config` | config_handler.go | 配置读写 |
| GET | `/api/config/dicts` | config_handler.go | 词典内容 |
| POST | `/api/config/reload` | config_handler.go | 重载词典 |
| GET | `/api/devices` | device_handler.go | 设备列表 |
| GET | `/api/snapshots/status` | snapshot_handler.go | 快照状态 |

#### `/api/alert-candidates` 核心参数

```
date_start, date_end       日期范围
target_type                目标类型
device_tags                设备标签名称（逗号分隔）
threat_types               威胁类型（逗号分隔）
hide_traced                隐藏已追踪
keyword                    关键词搜索
badges_filter              徽章筛选
page, page_size            分页
```

#### 返回关键字段

```json
{
  "items": [{
    "id", "device_id", "source_ip", "target", "port",
    "threat_type", "threat_level", "std_apt_org", "apt_org", "apt_org_tier",
    "first_alert_time", "last_alert_time", "alert_count",
    "badges": [{"name", "label", "color"}],
    "candidate_rule_ids", "candidate_reasons", "candidate_score",
    "candidate_priority": {"id", "label", "rank"},
    "target_kind", "heat": {...}, "device_tags": [...],
    "trace_status", "event_status"
  }],
  "total", "page", "page_size", "filter_options": {}
}
```

---

## 前端开发约定

- **框架：** Vue 3 (Composition API) + Vite + Element Plus
- **语言：** JavaScript（不用 TypeScript）
- **状态管理：** 组件本地状态 + composables，不需要 Pinia
- **HTTP 请求：** axios，封装在 `src/api/`
- **路由：** 5 个主页面（`/`, `/alerts`, `/events`, `/ioc-notes`, `/settings`）
- **构建产物：** `frontend/dist/`，Go 后端直接 mount 静态文件

---

## 候选评分规则

| 规则 | 字段 | 基础分 |
| ---- | ---- | ------ |
| 威胁类型命中APT | threat_type = apt | 34 |
| 威胁类型命中远控 | threat_type = 远控/remote | 30 |
| 已映射标准APT组织 | std_apt_org 非空 | 26 |
| 原始APT组织非空 | apt_org 非空 | 22 |

额外加分：威胁等级、APT分级、目标热度、设备热度、多厂商、事件关联、设备标签
减分：已追踪（活跃-12，过期-4）
优先级：≥110 高优先 / ≥75 中优先 / 其他 观察

---

## Badge 类型

| 名称 | 标签 | 颜色 | 触发条件 |
| ---- | ---- | ---- | -------- |
| apt_dict | APT词典 | red | std_apt_org 命中 APT 词典 |
| advanced_crime | 高级黑灰产 | purple | apt_org 命中高级黑产词典 |
| noise_family | 噪声家族 | gray | threat_type 命中噪声词典 |
| multi_vendor | 多厂商 | yellow | 厂商数 ≥ 3 |
| cross_day | 跨天持续 | green | 同源IP+目标跨天出现 |
| lateral | 横向扩散 | blue | 同源IP对 ≥3 个目标 |
| expired_revive | 追踪过期 | orange | 追踪超过TTL天数 |
| high_tier | 高级别 | gold | APT分级=一级 |
| scan_noise | 疑似扫描 | lightgray | 告警次数 > 1000 |

---

## 数据库表（PostgreSQL）

`alerts`, `mined_events`, `mined_event_devices`, `mined_event_iocs`, `event_followups`, `tags`, `tag_batches`（含 device_ids_snapshot 快照）, `device_tags`, `traced_targets`, `imports`（含 file_hash/queue_position）, `import_sheets`, `import_rows`, `audit_log`, `config`

**无快照表、无预计算表** — Go 版使用 CTE SQL 实时查询，不再需要快照机制。

**关键索引：** GIN 全文搜索索引（device_id/source_ip/target）、候选部分索引、事件 IOC 联合索引、设备标签联合索引、热度聚合索引。

---

## v4.0 核心设计原则

1. **没有快照表** — 所有查询是实时 SQL，不清缓存、不覆盖数据
2. **单一数据源** — 数据库存什么，API 就返回什么
3. **每个文件 ≤ 400 行** — 路由、服务、模型严格按职责拆分
4. **评分/Badge 在 SQL 中完成** — Go 只做序列化和分页
5. **goroutine 后台处理** — 导入不阻塞查询

---

## 开发注意事项

1. Go 后端在 `backend_v2/`，开发时 `cd backend_v2 && go run main.go`，生产 `go build` 为单 .exe
2. API 路径与 v3.x 保持一致，前端无需改动
4. 前端代理：开发时 Vite proxy → `http://127.0.0.1:8088`
5. 所有时间字段 `"YYYY-MM-DD HH:MM:SS"`
6. PostgreSQL 正式库 `apt_mining_prod`（8088），测试库 `apt_mining_test`（9099）
7. 导入是异步的：POST 后返回 job，需轮询 GET `/api/imports/{id}` 查状态

---

## 进度记录

> **AI 每完成一个阶段，必须在此处更新。格式：日期 + 阶段编号 + 完成内容摘要。**

| 日期 | 阶段 | 内容 |
| ---- | ---- | ---- |
| 2026-04-30 | 阶段0~5 | Python v3.x 前端重建：Vue3+Vite+Element Plus，4个页面（研判工作台/事件管理/原始告警/导入设置），暗色主题，API封装 |
| 2026-04-30~05-01 | 阶段6~11 | 全链路修复+性能优化：三主题切换、导入体验、候选SQL评分、IOC增强提取、事件自动打标 |
| 2026-05-02 | 阶段14~17 | 标签系统：去重修复、候选去重、批次增强、软删除 |
| 2026-05-06~07 | 阶段21~30 | v3.1 排序+筛选+UI打磨：Excel风格表头筛选、上传进度条、事件匹配IOC化、排序render函数修复、混合模式升级系统 |
| 2026-05-09 | 阶段31~43 | 迁移系统+筛选修复+候选去过滤：VERSION/CHANGELOG、Alembic框架、一键打包/上传/升级Python化、表头筛选全表范围、设备标签缓存失效 |
| 2026-05-11 | 阶段44~51 | 性能优化+快照设计：全量缓存分桶、列配置文件化、性能分析文档、快照表方案 v2 设计 |
| 2026-05-11~12 | 阶段52~62 | 快照实现+运维增强：快照表落地、运行脚本Python化、上传队列+Hash去重、清除上传数据 |
| 2026-05-14~15 | 阶段63~73 | 快照迭代+一致性修复：去快照化回退、预计算快照v3、快照底表+实时覆盖混合模型、事件按钮卡死修复 |
| 2026-05-16~18 | 阶段74~82 | 快照review修复+导入性能：大小写敏感修复、批量子表合并、SQLite连接池改为QueuePool、Excel流式读取移除全表扫描 |
| 2026-05-18~21 | v4.0 重写 | **Go 全栈重写完成**：(1)Phase 1 基础搭建——Go 1.22+Gin项目结构、PostgreSQL建表+索引、健康检查/版本/配置接口、migrations迁移脚本；(2)Phase 2 核心引擎——候选查询CTE SQL构建（candidate_service.go）、评分/Badge在SQL中完成、告警列表+筛选选项接口、Excel流式导入goroutine后台处理（import_service.go）、前端候选页对接新后端；(3)Phase 3 业务API——事件CRUD+IOC提取（event_handler.go/event_repo.go）、标签批次+批量打标（tag_handler.go/tag_repo.go）、追踪库管理（traced_handler.go/traced_repo.go）、设备列表（device_handler.go）；(4)Phase 4 前端迁移——Workbench/EventManager/AlertList/IocNotes/Settings 5个页面对接Go后端、列配置columns.json、表头筛选、主题切换；**已删除的代码**：snapshot_builder.py（1246行）、快照查询路径、候选缓存管理、patch_snapshot_for_* 散落在各文件的增量刷新，合计删除 ~2946 行Python补丁代码 |
| 2026-05-21 | v4.0 清理 | **旧 Python 后端及脚本全部删除**：`backend/` 目录（~50文件）、`requirements.txt`、`start.py/stop.py/start.bat/stop.bat/start-test.bat/stop-test.bat`、`install.py/bat/sh`、`export_ops_data.py/generate_demo_data.py/import_ops_data.py/recover_import.py`、`migrate_old_to_prod.py/migrate_sqlite_to_pg.py/migrate_test_to_prod.py`、`pack_release.py/push_release.py/upgrade.py`、`__pycache__/`、`venv/`；保留 Go 启动脚本（`go_import_and_start.bat/init_db.bat/startGo*.bat/stopGo*.bat`） |
| 2026-05-21 | v4.0 脚本修复 | **bat 脚本全面更新**：`startGo.bat`/`startGoTest.bat`/`go_import_and_start.bat` 从 `python start.py --go` 改为 `cd backend_v2 && apt-mining.exe`，直接启动编译好的 Go 可执行文件；`stopGo.bat`/`stopGoTest.bat` 使用 PowerShell 按端口杀进程无需修改；`init_db.bat` 末尾提示从"运行 import_ops_data.py"改为"双击 startGo.bat"；误删的 `go_import_and_start.bat` 重建完成 |
| 2026-05-21 | 运营数据导入修复 | **import_ops_data.py 重写**：从 psql 子进程改为 psycopg2 直连，解决 Windows GBK 编码导致中文乱码 bug；修复密码/用户名（apt_prod/apt_test）；修复表导入顺序（tag_batches 先于 tags 满足 FK 约束）；移除不存在的 config_data 表；在 apt_mining_test 测试库验证导入 6 条数据无 bug，API 返回中文正确 |
| 2026-05-21 | 根目录脚本全面修复 | **start.py**：移除 uvicorn/venv 路径，改为纯 Go 后端启动器，自动设置 DB 凭据；**install.py**：移除 venv/pip/requirements.txt，改为检查 Go+Node.js、go mod download、构建 Go 二进制、构建前端；**upgrade.py**：后端依赖安装改为 go mod download，数据库备份改为 pg_dump（PostgreSQL）；所有脚本通过语法检查，start.py/install.py/stop.py/upgrade.py --help 验证通过，install.py 全流程执行成功（Go 编译+前端构建） |
