# APT Mining Workbench v4.0 — AI 协作上下文

> **本文件是 AI 助手的上下文入口。每次新对话开始时，AI 必须先读取本文件。**
> **每完成一个阶段后，AI 必须更新底部的"进度记录"部分。**

---

## 使用方式

- 本文件分为默认规则与按需模式两层。
- 默认规则始终生效。
- 按需模式仅在用户明确要求，或任务明显需要且已获用户确认时启用；未启用前，不默认进入重流程。
- 涉及项目/系统设计、文档体系设计或高风险改动时，应在开始时让用户选择是否启用相关按需模式。

## 默认规则

### 工作原则

- 非微小改动先说明方法。
- 需求有歧义、风险高或影响大时，先澄清并获批，再开始写代码。
- 坚持 Spec Coding，避免 Vibe Coding；Plan 只写方案、范围、风险和验收标准，不写实现代码。
- 优先小步迭代；实现与审查分离。
- 完成后可执行 /simplify；必要时使用 /loop。

### 编码约束

- 代码中只使用英文。
- 注释说明意图、约束和边界，不记录开发过程式说明。
- 优先用概念、模块、职责和符号名定位代码；不要只依赖易漂移的行号，必要时可补充文件路径。
- Spec 不依赖行号定位代码。
- 不为未被请求的未来需求提前抽象、泛化或暴露配置。

### 质量与验证

- 项目早期只保留最小必要质量标准：可运行、可验证、可回滚。
- 关键路径、高风险改动和外部接口必须可验证。
- 修复 bug 时，先复现，再修复，再验证。
- 任何"已完成""已修复""已通过"的结论，都必须附验证方式、命令或结果摘要。
- 若当前无法验证，必须明确说明原因、风险和未覆盖范围。
- 修复 bug 或完成功能后，必须运行 `scripts/test_api.py` 全量回归测试，所有用例通过才算完成。

### 拆分与沉淀

- 将任务拆成低耦合、可独立验证的子任务；必要时使用 /batch。
- 重复出现且边界稳定的流程，应沉淀为 Skill、脚本或检查清单。
- 公共规则优先沉淀为文档、测试或自动化，而不是只停留在对话里。

### 协作与纠错

- 被纠正时，先验证问题是否适用于当前代码库，再调整做法。
- 外部建议先核对是否适用，再决定是否采纳。
- 对重复性问题，沉淀为明确规则、测试或自动检查。

### Codex 协作

- Codex 是补充能力，不是默认执行者；当前 Agent 负责主线推进、需求澄清、关键决策、首轮实现和最终验收。
- 仅在以下场景使用 Codex：独立只读代码评审、adversarial review、边界清晰且可并行的子任务、或长耗时调查与后台续跑；委派前必须先定义目标、约束、验收标准和边界。
- 不要把需求澄清、方案收敛、架构取舍、小而集中的直接实现或需要持续用户交互的主线任务交给 Codex；Codex 的结果必须由当前 Agent 整合并复核。
- 可用命令：`/codex:review`、`/codex:adversarial-review`、`/codex:rescue`、`/codex:status`、`/codex:result`、`/codex:cancel`（需安装 [codex-plugin-cc](https://github.com/openai/codex-plugin-cc)）

### 禁止事项

- 永远不要使用 /init，除非项目明确要求。
- CLAUDE.md 必须按项目实际需求编写，不套用空泛模板。
- 不要在代码注释、commit message 或 PR body 中使用描述开发进度的词，如 FIXED、Step、Week、Section、Phase、AC-x。
- 不要在代码注释、commit message 或 PR body 中出现 AI 工具名称，如 Codex、Claude、Grok、Gemini 等。
- 不要把外部实现细节、外部文档或外部技能树直接提升为当前项目的硬约束。

## 按需模式

### 架构与演进模式

- 适用：用户要求项目或系统设计满足分层、稳定接口、可演进，或明确要求按架构流程推进。
- 优先做分层设计；不同层次保持职责分离，只通过明确、稳定的接口交互。
- 不要让上层依赖下层实现细节，也不要建立非必要的跨层耦合；若必须依赖，应收敛为单向、最小依赖。
- 每个层次内优先做 primitive 设计；primitive 应是独立、可替换、可组合、可验证的最小功能单元。
- 若项目采用多 Agent 协作，应按层次设计专用 agent 与 skill，使其职责、输入、输出和边界清晰。
- 架构演进必须逐步验证；每一步新增特性或重构，都要确认不破坏已有接口、行为和关键路径。

### Agent-Native 文档模式

- 适用：用户要求文档同时服务人类和 Agent，或明确要求 Agent-Native 文档体系。
- 使用两层结构，避免重复：
  - canonical skill docs (.claude/docs/)：保存详细、长期维护的正式正文，供人类和 Agent 共读。
  - agent-facing index（.claude/skills/）：只负责把 Agent 路由到正确正文，不复述内容，也不要求与每份正文一一对应。
- 文档应同时对人类和 Agent 可读：写清能力、前提、边界、依赖、接口和典型用法，避免只对单一读者成立的隐式上下文。
- 仅 skill 文档必须包含 frontmatter：type、tags、requires（仅写硬依赖）。
- Agent 读取文档时，先通过索引定位主题，再进入正文；仅递归读取 requires 指向的硬依赖文档，其他相邻或参考文档按需读取。
- 本地文档是当前仓库契约；外部资料、外部 skills 或示例实现只作参考，不覆盖本地约定。
- 量化结论必须带测试条件和适用范围。

### 严格验证模式

- 适用：改动高风险、回归代价高，或用户要求每一步都经过验证。
- 将工作拆成可独立验证的小步；每一步完成后先验证，再继续下一步。
- 新增特性、重构或修复都要确认不破坏已有功能、接口和关键路径。
- 若当前无法完成必要验证，应暂停继续扩展，并明确说明阻塞、风险和未覆盖范围。

---

## 项目概述

APT 挖掘工作台：安全分析师从海量网络告警中挖掘 APT 事件的单机离线平台。

**技术栈：** Go 1.22 + Gin + PostgreSQL（后端） / Vue 3 + Vite + Element Plus（前端）
**运行方式：** 本地启动，浏览器访问 `http://127.0.0.1:9099`（端口在 `.env` 中配置）
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

1. Go 后端在 `backend_v2/`，开发时 `python dev.py`（go run 直接跑最新版），发布时 `python install.py`（编译+前端构建+同步），`python start.py` 会自动检测源码变化并重新构建
2. API 路径与 v3.x 保持一致，前端无需改动
3. 前端代理：开发时 Vite proxy → `http://127.0.0.1:9099`
4. 所有时间字段 `"YYYY-MM-DD HH:MM:SS"`
5. 数据库连接统一由根目录 `.env` 文件管理（APT_DB_HOST/PORT/USER/PASSWORD/NAME、APT_SERVER_PORT）
6. 导入是异步的：POST 后返回 job，需轮询 GET `/api/imports/{id}` 查状态

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
| 2026-05-21 | Excel 上传修复 | **修复上传 Excel 失败问题**（所有 112,805 行全部失败）：(1) 表头映射不匹配 — Excel 实际列名 `外联端口`/`APT组织`/`APT组织分类` 与 Go 代码期望的 `端口`/`原始APT组织`/`APT分级` 不一致，修改 `extractRow` 支持双名称回退；(2) SQL INSERT 语法错误 — `ON CONFLICT (content_hash) DO NOTHING` 依赖唯一索引但迁移中创建的是普通索引，改为 `INSERT ... SELECT ... WHERE NOT EXISTS` 实现去重；(3) 后端增强 — `uploads/` 目录自动创建、multipart 上传限制提升至 500MB；(4) 前端修复 — `handleUploadExcel` 期望 `result.jobs` 数组但后端返回单个对象，修正为兼容两种格式；(5) axios 错误拦截器增加 `error` 字段解析（后端返回 `{"error": "..."}` 而非 `{"detail": "..."}`） |
| 2026-05-21 | Review 修复 | **响应 review 反馈修复两处回归**：(1) **统计失真修复** — `INSERT ... WHERE NOT EXISTS` 即使 0 行插入也不返回 error，原代码直接 `totalInserted++` 把重复行误计为成功；改为检查 `result.RowsAffected()`，affected=0 时计入 `totalSkipped`，导入历史和详情页的 `rows_inserted`/`rows_skipped` 统计恢复准确；(2) **数据库级去重说明** — 尝试创建 `content_hash` UNIQUE 索引（`002_alerts_content_hash_unique.up.sql`），但 `apt_prod` 用户不是 alerts 表属主，无权限创建唯一索引；当前采用 `WHERE NOT EXISTS` 应用层去重（在同一条语句内有效），对于 DBA 环境用户可手动执行 `CREATE UNIQUE INDEX idx_alerts_content_hash_unique ON alerts(content_hash)` 获得数据库级去重保证；已删除失败的迁移文件避免启动日志噪声 |
| 2026-05-21 | Git 忽略修复 | **`backend_v2/.gocache/` 纳入 `.gitignore`** — Go 编译缓存目录 `backend_v2/.gocache/` 未被忽略，导致 `git status` 显示大量未追踪缓存文件，push/pack 脚本会将其误包含进发布包；在 `backend_v2/.gitignore` 追加 `.gocache/`，验证 `git status` 不再列出该目录 |
| 2026-05-21 | 发布脚本修复 | **pack/push 脚本排除 `.gocache/`** — `pack_release.py` 的 `EXCLUDE_DIRS` 追加 `.gocache`，打包时不再复制 Go 编译缓存；`push_release.py` 的 `GIT_EXCLUDE` 追加 `.gocache/`，`git add -A` 后自动 reset 该目录，推送时不再包含缓存文件 |
| 2026-05-21 | VERSION 统一 | **统一使用根目录 VERSION 文件** — (1) 删除 `backend_v2/VERSION`（旧版本 3.3.7）；(2) `backend_v2/internal/handler/health.go` 的 Version handler 改为先读取 `../VERSION`（项目根目录），回退到本地 `VERSION`；(3) `pack_release.py` 的 `copy_ignore_func` 追加排除子目录中的 `VERSION` 文件，避免打包时从 `backend_v2/` 复制旧版本；(4) `upgrade.py` 的 `_merge_dir` 增加 `skip_version` 参数，升级时不再覆盖子目录中的 VERSION 文件；根目录 `pack_release.py`/`push_release.py`/`upgrade.py` 原本就指向根目录 VERSION，无需修改 |
| 2026-05-21 | 脚本可用性修复 | **统一 Go 构建缓存并修正文档/提示** — `install.py`/`start.py`/`pack_release.py`/`upgrade.py` 统一将 `GOCACHE` 指向 `backend_v2/.gocache`，规避 Windows 全局 Go 缓存权限导致的构建失败；`upgrade.py` 移除过时的 `start.py --go`/`start.bat` 提示；`startGo.bat` 增加缺失 `apt-mining.exe` 的明确引导；`README.md` 启动说明改为先 `init_db.bat`，并统一 `backend_v2` 路径与 `python start.py` 用法 |
| 2026-05-21 | v4.0.1 研判工作台修复 | **修复 5 个研判工作台 bug**：(1) **表头筛选无内容** — `GET /api/alert-candidates` 响应增加 `filter_options` 字段，重写 `GetFilterOptions()` 返回 `map[string][]string`，新增 device_id/source_ip/port/std_apt_org/device_tags 筛选选项；设备id列增加 el-popover 筛选图标和搜索功能；(2) **设备ID计数全为0** — 前端 `heat.device_target_count` 改为 `heat.target_device_count`，与后端 `HeatInfo.target_device_count` 一致；(3) **源IP计数全为1** — 后端 SQL 增加 `source_ip_count` 输出（取自 `heat_source_ip_alert_count`），`CandidateItem`/`CandidateRow` 增加字段，前端去除 `?? 1` 硬编码回退；(4) **事件提交未识别设备ID** — 保持设备ID从单行提取逻辑不变，确认后端 `CreateEvent` 正确接收 `devices` 数组；(5) **事件提交失败** — 前端 `submitEvent` 将 `iocs` 从 `[{target, port}]` 对象数组改为 `["target:port"]` 字符串数组，匹配后端 `event_handler.go` 的 `IOCs []string` 期望 |
| 2026-05-22 | v4.1 Go 平台打磨 | **v4.0 → Python v3.x 功能逐项对照**：(1) 逐阶段对照旧 Python 版 82 个阶段优化项，确认 Go 版已实现 10/11 项（repair-metadata、批次详情/恢复、排除标签筛选、标签颜色 PATCH、清除全部上传数据、轮询失败计数器、表头筛选"确定"按钮、设备ID计数算法均已在 Go 版中实现）；(2) **唯一缺失：hide_closed 端口通配** — `candidate_repo.go` 中 `hide_closed` 的 WHERE 子句原用精确匹配 `COALESCE(mei.port, '') = COALESCE(a.port, '')`，改为 `(COALESCE(mei.port, '') = COALESCE(a.port, '') OR mei.port = '*')` 支持通配端口，事件 IOC 端口为 `*` 时可匹配该目标所有告警 |
| 2026-05-22 | v4.6 全链路回归测试 | **9 项核心功能回归测试通过**（基于 apt_mining_test 测试库，12552 条告警数据）：(1) 创建标签+批量打标设备；(2) 添加 IOC 备注；(3) 创建事件（关联 IOC+设备+跟进记录）；(4) 事件关闭→再激活；(5) 编辑 IOC 备注；(6) 编辑事件（名称、颜色、备注）；(7) 删除设备标签；(8) 批次软删除→恢复（soft-delete status=deleted → restore restored_count=1）；(9) hide_closed 端口通配修复验证（通配端口 `*` 正确过滤 9 条匹配告警）；(10) 设备标签筛选 API（单标签 201 条 / 多标签 OR 201 条 / 排除标签 12351 条）；(11) 表头排序测试（11 个字段 ASC/DESC 全部通过，非法字段安全回退默认排序，筛选+排序组合验证通过） |
| 2026-05-22 | v4.7 设备ID计数修复+静态文件同步 | **根因：Go 后端从 `backend_v2/static/` 提供静态文件，不是 `frontend/dist/`** — `static/` 中是旧构建产物（5月21日 `index-DLVyS5yF.js`），不含 `device_id_count` 字段；最新构建 `frontend/dist/`（5月22日 `index-Btm2SLbx.js`）已包含修复；**修复**：将 `frontend/dist/*` 同步到 `backend_v2/static/`，删除旧 assets；**验证**：HTML 引用新 JS、API 返回 `device_id_count: 201`、JS 文件包含 `device_id_count` 字段，全链路通过（测试库 12552 条数据）；**设备ID计数算法**：SQL `device_heat` CTE 按 device_id 分组 `COUNT(*)`，出现一行设备ID即+1；**流程修复**：`install.py` 新增 `sync_static()` 步骤（`[4/5] Syncing frontend static files`），构建前端后自动将 `frontend/dist/` 复制到 `backend_v2/static/`，不再需要手动同步 |
| 2026-05-22 | v4.7.1 device_id_count 排序修复 | **修复测试平台 `device_id_count` 排序报错**：(1) **根因** — `candidate_repo.go` 的 `scored` CTE 中 `device_id_count` 仅在 `json_build_object` 中作为键名存在（第 373 行 `'device_id_count', heat_device_alert_count`），不是 CTE 的真实输出列；`ORDER BY %s %s` 动态排序时引用 `device_id_count`，PostgreSQL 在 CTE 列中找不到该字段报 42703 错误；(2) **修复** — 在 `scored` CTE 的 SELECT 中增加 `COALESCE(dh.device_alert_count, 1) AS device_id_count`（第 307 行），使 `device_id_count` 成为 CTE 的真实输出列，`ORDER BY` 可直接引用；(3) **验证** — 测试库 `sort_by=device_id_count&sort_order=DESC` 返回 device_id_count=2916（最大值）、`sort_order=ASC` 返回 device_id_count=1（最小值），均正常无报错 |
| 2026-05-22 | v4.7.2 分页容量提升+滚动条加宽 | **研判工作台默认每页 1000 条**：(1) `Workbench.vue` 默认 `pageSize` 从 50 改为 1000；(2) 分页器 `page-sizes` 改为 `[1000, 2000, 5000]`；(3) 分页器按钮宽度加至 96px（约 3 倍原宽），选择器宽度 120px，字号/间距同步放大；**滚动条加宽**：(4) `global.css` `::-webkit-scrollbar` 从 10px 改为 14px，暗色/浅色主题滚动条颜色变量保持不变；(5) 前端构建产物同步至 `backend_v2/static/` |
| 2026-05-22 | v4.7.3 日期范围筛选修复 | **修复日期范围筛选结果与原始数据不符**：(1) **根因** — `candidate_repo.go:60` 的 `date_end` 使用 `<= $N` 比较，PostgreSQL 将 `'2026-05-15'` 解析为 `'2026-05-15 00:00:00'`，导致结束日期的全天数据被截断（仅包含 00:00:00 时刻）；选"14日" → `>= '2026-05-14 00:00:00'` AND `<= '2026-05-14 00:00:00'` → 仅匹配午夜时刻的几条记录；选"14-15日" → 包含14日全天 + 15日0点，15日几乎无数据；(2) **修复** — 改为 `a.first_alert_time < ($N::date + interval '1 day')`，即 `< '2026-05-16 00:00:00'`，结束日期包含全天 23:59:59 的数据；(3) **验证** — Go 编译通过，前端构建产物同步至 `backend_v2/static/` |
| 2026-05-22 | v4.7.4 滚动条加宽 | **滚动条宽度从 14px 改为 28px（2 倍）**：(1) `global.css` `::-webkit-scrollbar` width/height 从 14px 改为 28px，暗色/浅色主题滚动条颜色变量保持不变；(2) 前端构建产物同步至 `backend_v2/static/` |
| 2026-05-22 | v4.7.5 日期筛选后转圈动画卡死修复 | **修复日期筛选后前端 loading 转圈动画卡死**：(1) **根因** — `Workbench.vue` 的 `displayData` computed 属性内部修改了 `total.value`（第 1386 行 `total.value = filtered.length`），在 Vue 响应式系统中产生级联更新循环：computed 求值 → 修改 total → 触发依赖 total 的其他 computed/template 更新 → 再次求值 displayData → 再次修改 total，当每页 1000 条数据时，单次求值涉及 1000 行 filter + 8 列 filter 检查，响应式 cascade 阻塞 UI 主线程导致 spinner 卡死；(2) **修复** — 将 `total.value` 赋值从 `displayData` computed 中移除，改为 `displayTotal` computed 内部通过 `displayData.value.length` 计算本地筛选后的总数，消除响应式副作用；(3) 前端构建产物同步至 `backend_v2/static/` |
| 2026-05-22 | v4.7.6 启动脚本防旧版本修复 | **修复启动后端仍跑旧版本的回归**：(1) **根因** — `start.py` 仅在 exe 不存在时构建，源码更新后直接 `python start.py` 会跳过编译跑旧 exe；(2) **修复** — `start.py` 新增 `needs_rebuild()` 函数，递归检查 `backend_v2/` 下所有 `.go` 文件的 mtime 是否比 exe 新，自动触发重新构建；新增 `--no-rebuild` 参数可跳过此检查；(3) **新建 `dev.py`** — 开发模式启动脚本，用 `go run main.go` 直接跑最新代码，无需手动 build，支持 `--test`/`--no-browser`/`--host`/`--port` 参数，功能与 `start.py` 对齐（杀进程、开浏览器、.env 加载、端口冲突处理） |
| 2026-05-23 | v4.8 对齐 3.2.10 功能修复 | **以 3.2.10 为行为基线，修复 5 项缺失功能**（对齐计划 15 项全量回归测试通过）：(1) **P0-1 追踪减分** — `candidate_repo.go` SQL 评分新增 traced 减分项：活跃追踪 -12 分、过期追踪 -4 分，与 3.2.10 `alert_workbench.py:229-232` 一致；traced CTE 从硬编码 `'active'` 改为基于 `trace_ttl_days` 的 TTL 动态计算 active/expired 状态；(2) **P0-2 Badge 补全** — `candidate_service.go` `computeBadges()` 从 5 种补全到 9 种：新增 `advanced_crime`（高级黑灰产词典匹配）、`cross_day`（跨天持续 SQL 预计算）、`lateral`（横向扩散 SQL 预计算）、`expired_revive`（利用 traced CTE 的 expired 状态）；修复 `apt_dict` 从空判断改为 APT 词典精确匹配；修复 `noise_family` 使用噪声词典文件；(3) **P0-3 badges_filter 后端过滤** — `candidate_service.go` 新增 `repoQueryWithBadgeFilter()`，当 badges_filter 参数非空时放大查询 page_size 10 倍，在 Go 层按 badge name/label 过滤后分页返回；(4) **P1-6 filter_options 补全** — `candidate_repo.go` `GetFilterOptions()` 新增 `priority`（["高优先", "中优先", "观察"]）、`badges`（9 种 badge label）、`ioc_note`（null）三个缺失键；(5) **P3-14 TXT 导入预设** — `tag_handler.go` `ImportTextFiles()` 新增文件名→标签预设匹配："01排查成功"→排查成功(绿)、"02重点设备"→重点设备(红)、"03不好查"→不好查(灰)，与 3.2.10 `TXT_TAG_IMPORT_PRESETS` 完全一致；**回归验证 15 项全部通过**：追踪减分(score=179/-12, score=187/-4)、Badge 7 种可实现全部找到、badges_filter 跨页过滤(943 项匹配)、filter_options 10 键完整、日期范围筛选(单日 1428 项)、排序 3 项验证、device_id_count/source_ip_count 正确、hide_closed 端口通配支持、TXT 预设 9 种场景单元测试通过、健康检查和候选数据端点正常 |
| 2026-05-24 | v4.9 对齐 3.2.10 核心行为修复（第1批） | **以 3.2.10 为行为基线，修复 4 项 P0/P1 核心 bug + 1 项 DB 连接修复**（方案 A 逐项修复）：(1) **BUG-01 候选去重** — `candidate_repo.go` `base` CTE 改为 `ROW_NUMBER() OVER (PARTITION BY device_id, target, COALESCE(port,'') ORDER BY alert_count DESC, last_alert_time DESC, id DESC)` 去重，与 3.2.10 阶段15 一致；(2) **BUG-02 事件自动打标签+跟进记录** — `event_repo.go` `CreateEventTx` 新增：(a) 插入 `event_followups` 记录 `action_type='note'` 内容"创建事件: {event_name}"；(b) 查找或创建 `"事件挖掘: {event_name}"` 永久标签（`is_permanent=1`）；(c) 为每个设备插入 `device_tags` 记录；`UpdateEvent` 增加 status 变更自动插入 `action_type='status_change'` 跟进记录；(3) **BUG-10 导入级联删除** — `import_service.go` `DeleteImport` 按序级联删除：alerts(import_id) → import_rows → import_sheets → imports，与 3.2.10 阶段23 一致；(4) **BUG-16 UpdateEvent 空值覆盖** — `event_repo.go` `UpdateEvent` 改为只更新非空字段（前端只传 status 时不会清空 name/color/note）；(5) **DB 连接修复** — `db.go` 连接字符串改为 URL 格式 `postgres://user:pass@host:port/dbname`，解决空密码时 `pq` 驱动忽略 dbname 参数、错误连接到 postgres 默认库的 bug；**回归验证通过**：候选去重 233940 条数据 0 重复、事件创建自动标签+跟进记录成功、UpdateEvent 部分更新保留原字段、Go 单元测试全部通过 |
| 2026-05-24 | 配置统一 | **统一数据库和端口配置到根目录 `.env` 文件**：(1) 新建 `.env` 含 `APT_DB_HOST/PORT/USER/PASSWORD/NAME` 和 `APT_SERVER_PORT=9099`；(2) 删除旧的 PROD/TEST 双变量体系（`APT_DB_USER_PROD`、`APT_DB_NAME_TEST` 等 6 个变量合并为 `APT_DB_USER`、`APT_DB_NAME` 等）；(3) `db.go` 默认值改为 `apt_test`/`apt_mining_test`；(4) `start.py`/`dev.py`/`stop.py` 端口默认从 `.env` 读取（9099）；(5) `upgrade.py` 排除 `.env` 不被覆盖，备份数据库名从 `.env` 读取；(6) `import_ops_data.py` 移除 `--test` 参数，直接读 `.env`；(7) `init_db.bat` 简化为读 `.env` 变量；(8) `frontend/vite.config.js`/`App.vue` 默认端口改为 9099；(9) `config/config.yaml` 端口改为 9099；(10) 删除冗余 `backend_v2/.env.example` |
| 2026-05-24 | v4.10 对齐 3.2.10 功能修复（第2批） | **以 3.2.10 为行为基线，修复 8 项 P0/P1/P2 功能 bug**：(1) **P0-1 import_rows 写入** — `import_service.go` `processImport` 新增每行写入 `import_rows` 表（parsed/skipped_duplicate/failed 三种状态，含 raw_json 和 alert_id），修复导入详情页行明细始终为空；(2) **P0-2 GetImportRows SQL 修复** — 补全 `SELECT ir.* FROM import_rows ir` 前缀，解决 SQL 语法错误；(3) **P1-1 中文关键词搜索** — `candidate_repo.go` 关键词搜索从 `to_tsvector('simple')` GIN 全文搜索改为 `ILIKE '%keyword%'` 跨 6 字段模糊匹配，支持中文子串搜索；(4) **P1-2 hide_traced 端口通配** — `candidate_repo.go` `HideTraced` 条件从精确匹配改为 `COALESCE(tt.port, '') IN ('', COALESCE(a.port, ''))`，追踪记录端口为空时匹配所有告警端口；(5) **P1-3 辅助字段补全** — `model.go` 新增 `target_kind_label`、`trace_status_label`、`device_note_summary`、`heat_summary` 四个显示辅助字段，`candidate_service.go` `rowToItem` 中计算填充；(6) **P1-4 ListImports 时间格式** — 改为强类型 `sql.NullTime` 扫描 + `YYYY-MM-DD HH:MM:SS` 格式化，不再返回 RFC3339；(7) **P1-5 content_hash SHA256** — `computeContentHash` 从 32-bit 多项式滚动哈希改为 `crypto/sha256`，降低碰撞风险；(8) **P1-6 IOC 提取器对齐** — `ioc_extractor.go` 新增 `network:/domain:/dns:` 前缀剥离（`stripPrefix`）、可执行文件扩展名过滤、URL hostname 去重、中文字符支持增强；**验收测试通过（10/10 场景 + 15 单元测试）**：(a) Go build/vet/test 全通过；(b) 中文搜索 keyword=银狐 正确匹配 std_apt_org；(c) hide_traced 筛选 12552→12504 无报错；(d) ListImports 返回 `"imported_at":"2026-05-21 12:17:47"` 格式正确；(e) GetImportRows SQL 无语法错误；(f) IOC 提取 `network:evil.com`→`evil.com` 前缀已剥离、`malware.exe` 已过滤、`phishing.com` 无重复；(g) 候选响应含 `target_kind_label`/`device_note_summary`/`heat_summary` 辅助字段 |
| 2026-05-25 | v4.11 事件提交 IOC 格式修复 | **修复 4.7.6 事件提交接口 IOC 格式不兼容**（对齐 3.2.10）：(1) **根因** — `event_handler.go` 的 `CreateEvent` 和 `AddIOCs` handler 定义 `IOCs []string`（期望 `["target:port"]` 字符串数组），但前端 EventManager 发送 `[{target, port}]` 对象数组（与 3.2.10 Python 版一致），Go 无法将对象反序列化为字符串，报 `json: cannot unmarshal object into Go struct field .iocs of type string`；(2) **CreateEvent 修复** — `event_handler.go:54` `IOCs []string` → `IOCs []repository.IOC`，line 61-67 移除 `h.Extractor.ExtractIOCs()` 字符串解析，改为直接使用对象 `Target: strings.TrimSpace(ioc.Target), Port: strings.TrimSpace(ioc.Port)`；(3) **AddIOCs 修复** — `event_handler.go:147` `IOCs []string` → `IOCs []repository.IOC`，line 153-159 移除 `strings.SplitN` 拆分，改为直接使用对象；(4) **Workbench.vue 修复** — line 1000 `eventForm.iocs` 初始化从字符串 `[iocStr]` 改为对象 `[{ target, port }]`，submitEvent 直接透传；(5) **回归验证 12/12 通过**：Go build/vet 通过、18 子测试全通过、无残留 `strings.SplitN`、TrimSpace 保留、ExtractIOCs handler 未受影响、前端构建成功、static/ 已同步 |
| 2026-05-25 | v4.12 事件恢复活跃色板同步修复 | **修复事件恢复活跃时色板仍显示蓝色的问题**：(1) **根因** — `EventManager.vue` 的 `handleStatusChange` 关闭事件时同步设置 `editColor.value = '#409EFF'`（色板变蓝），但恢复活跃时只通过 API 发送 `payload.color = '#FF5722'`（数据库变红），**未同步更新 `editColor.value`**，导致色板仍显示蓝色而实际颜色已是红色；(2) **修复** — line 449 新增 `else if (val === 'active') editColor.value = '#FF5722'`，恢复活跃时色板同步变为红色；(3) 前端构建产物同步至 `backend_v2/static/` |
| 2026-05-25 | v4.14 事件匹配大小写修复 | **修复创建事件后研判工作台对应 IOC 不显示事件**：(1) **根因** — `candidate_repo.go` 第 367 行 `events` CTE JOIN 使用精确比较 `e.target = a.target`，无大小写归一化；Excel 导入的 target（如 `MASKED_DOMAIN_19571.COM`）与用户创建事件时输入的 target（如 `masked_domain_19571.com`）大小写不同，JOIN 匹配失败；(2) **修复** — `candidate_repo.go` 第 367 行改为 `UPPER(e.target) = UPPER(a.target)` + 新增通配端口 `OR e.port = '*'` 支持（对齐 HideClosed 已有行为）；第 368 行 `traced` CTE JOIN 同样加 `UPPER()` 归一化；`event_repo.go` 的 `CreateEventTx` 和 `AddIOCs` 插入 IOC 时对 target 加 `strings.ToLower()` 存储归一化（双重保险）；(3) 验证：Go build/vet 通过 |

