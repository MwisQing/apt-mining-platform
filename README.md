# APT Mining Workbench

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Go 1.22+](https://img.shields.io/badge/Go-1.22+-00ADD8.svg)](https://go.dev/)
[![Vue 3](https://img.shields.io/badge/Vue-3.x-brightgreen.svg)](https://vuejs.org/)
[![PostgreSQL 15+](https://img.shields.io/badge/PostgreSQL-15+-336791.svg)](https://www.postgresql.org/)

安全分析师从海量网络告警中挖掘 APT（高级持续性威胁）事件的单机离线工作台。

> 每天面对10万+告警，自动化筛选候选、评分排序、去重聚合，把真正需要人类研判的事件从噪声中捞出来。

## 为什么做这个

安全运营中，告警量巨大但真正有价值的不足1%。现有方案要么是重型SIEM/SOAR平台（部署复杂、成本高），要么是手工脚本（不可维护）。这个项目提供一种**中间路线**：

- **单机离线**：一个 `go run main.go` 就能跑，Windows 平台双击 `startGo.bat`
- **CTE SQL 评分**：所有计算在 SQL 中完成，Go 只做序列化和分页
- **研判闭环**：从告警导入 → 候选筛选 → 创建事件 → 标记追踪 → 下次自动命中

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 后端语言 | Go 1.22+ | 编译为单 .exe 文件部署 |
| Web 框架 | Gin | 轻量高性能 HTTP 框架 |
| 数据库 | PostgreSQL 15+ | 并发读写、并行查询、GIN 全文搜索索引 |
| 前端框架 | Vue 3 + Element Plus | Composition API，组件化拆分 |
| 前端构建 | Vite | 生产产物挂载到 Go 静态文件服务 |
| 部署 | 单 .exe + PostgreSQL 服务 | Windows 平台 |

## 快速开始

### 环境要求

- **Go** 1.22+
- **PostgreSQL** 15+

### 一键启动（Windows）

双击 `startGo.bat`，自动初始化数据库并启动后端服务。

浏览器访问 `http://127.0.0.1:8088`

### 手动启动

```bash
# 1. 初始化 PostgreSQL 数据库（首次运行）
init_db.bat

# 2. 启动后端
cd backend
go run main.go

# 生产环境：编译为单文件
go build -o apt-mining.exe
```

### 测试实例

双击 `startGoTest.bat`，启动在 `9099` 端口的测试实例，数据完全隔离。

### 开发模式

```bash
# 后端（终端1）
cd backend
go run main.go

# 前端（终端2）
cd frontend
npm run dev  # Vite 开发服务器，自动代理 API 到 8088
```

## 用户工作流

```
┌─────────────────────────────────────────────────────────────┐
│  1. 上传告警 Excel（10万+行）→ 导入平台                       │
│  2. 导入设备标签 TXT → 批量打标（排查成功/重点设备/不好查）      │
│  3. 研判工作台 → 候选结果（自动筛 APT/远控、评分排序、去重）      │
│  4. 逐条研判：有价值 → 创建事件 │ 已知 → 标记追踪               │
│  5. 下次导入新数据 → 标签和追踪自动生效                        │
└─────────────────────────────────────────────────────────────┘
```

## 项目结构

```
apt-mining-platform/
├── backend/                    # Go 后端
│   ├── main.go                 # 入口：Gin 路由 + PostgreSQL + 静态文件
│   ├── go.mod / go.sum
│   ├── internal/
│   │   ├── handler/            # HTTP 请求处理（每个 ≤ 200 行）
│   │   ├── service/            # 业务逻辑（CTE SQL 构建、Excel 流式解析）
│   │   ├── repository/         # 数据库操作
│   │   ├── model/model.go      # 数据结构体
│   │   └── config/config.go    # YAML 配置加载
│   └── migrations/             # PostgreSQL 迁移 SQL
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── views/              # 5 个页面（每个 < 300 行壳）
│   │   │   ├── Workbench.vue   # 研判工作台（核心）
│   │   │   ├── AlertList.vue   # 原始告警列表
│   │   │   ├── EventManager.vue # 事件管理
│   │   │   ├── Settings.vue    # 导入与设置
│   │   │   └── IocNotes.vue    # IOC 备注管理
│   │   ├── api/                # axios 封装
│   │   ├── composables/        # 组合式函数（列配置、筛选等）
│   │   └── router/             # Vue Router
│   ├── dist/                   # 生产构建产物
│   └── public/columns.json     # 列配置文件
├── config/                     # 词典文件
│   ├── config.yaml
│   ├── apt_org_dict.yaml
│   ├── advanced_crime.yaml
│   └── noise_family.yaml
├── data/                       # PostgreSQL 数据目录
├── uploads/                    # 上传文件暂存
├── docs/superpowers/
│   ├── specs/                  # 设计文档
│   └── plans/                  # 实施计划
├── CHANGELOG.md
├── VERSION
└── README.md
```

## 核心 API

### 告警与候选

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/alert-candidates` | **候选结果（核心）**：CTE SQL 评分，分页排序 |
| GET | `/api/alerts` | 原始告警列表（分页、筛选） |
| GET | `/api/alerts/options` | 动态筛选选项 |
| POST | `/api/alerts/export` | 导出告警 xlsx |

候选返回字段：`candidate_score`、`candidate_priority`、`candidate_reasons`、`badges`、`heat`、`device_tags`、`trace_status`、`event_status`。

### 事件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/events` | 事件列表 / 创建 |
| GET/PATCH/DELETE | `/api/events/{id}` | 事件 CRUD |
| POST | `/api/events/{id}/followups` | 添加跟进记录 |
| POST/DELETE | `/api/events/{id}/devices` | 关联/移除设备 |
| POST/DELETE | `/api/events/{id}/iocs` | 关联/移除 IOC |

### 标签 / 追踪 / 导入 / 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/tags/batches` | 标签批次 CRUD |
| POST | `/api/tags/batches/import-text-files` | TXT 批量打标 |
| GET/POST/DELETE | `/api/tags/devices/...` | 设备标签 |
| GET/POST/PATCH/DELETE | `/api/traced` | IOC 追踪管理 |
| POST/GET/DELETE | `/api/imports` | 上传 Excel / 导入管理 |
| GET/POST | `/api/config` | 配置读写 |
| GET | `/api/health` | 健康检查 |

## 数据库

PostgreSQL，14 张表，无快照表、无预计算表。

| 表名 | 说明 |
|------|------|
| `alerts` | 告警主表（含评分字段、Badge 标记） |
| `mined_events` | 事件主表 |
| `mined_event_devices` / `mined_event_iocs` | 事件关联表 |
| `event_followups` | 事件跟进记录 |
| `tags` / `tag_batches` / `device_tags` | 标签系统 |
| `traced_targets` | IOC 追踪库 |
| `imports` / `import_sheets` / `import_rows` | 导入溯源 |
| `config` | 系统配置 |

**关键索引：** GIN 全文搜索（device_id/source_ip/target）、候选部分索引、事件 IOC 联合索引、热度聚合索引。

## 候选评分引擎

评分在 PostgreSQL SQL（CTE + CASE WHEN）中完成，Go 仅做序列化。

| 规则 | 触发条件 | 得分 |
|------|----------|------|
| 威胁类型命中 APT | `threat_type` = apt | 34 |
| 威胁类型命中远控 | `threat_type` = 远控/remote | 30 |
| 已映射标准 APT 组织 | `std_apt_org` 非空 | 26 |
| 原始 APT 组织非空 | `apt_org` 非空 | 22 |

**加分项**：威胁等级、APT 分级、目标热度、设备热度、多厂商、事件关联、设备标签
**减分项**：已追踪活跃 -12、追踪过期 -4

| 分数 | 标签 | 颜色 |
|------|------|------|
| ≥ 110 | 高优先 | 红 |
| ≥ 75 | 中优先 | 橙 |
| < 75 | 观察 | 灰 |

## v4.0 核心设计原则

1. **没有快照表** — 所有查询是实时 CTE SQL，不清缓存、不覆盖数据
2. **单一数据源** — 数据库存什么，API 就返回什么
3. **每个文件 ≤ 400 行** — handler / service / repository 严格职责拆分
4. **评分/Badge 在 SQL 中完成** — Go 只做序列化和分页
5. **goroutine 后台处理** — Excel 导入 goroutine 顺序处理，不阻塞查询

## 已知限制

- **单机设计**：适合安全分析师个人使用
- **Windows 优先**：启动脚本为 `.bat`，Linux/macOS 需手动 `go run main.go`
- **PostgreSQL 依赖**：需安装并运行 PostgreSQL 服务

## License

MIT
