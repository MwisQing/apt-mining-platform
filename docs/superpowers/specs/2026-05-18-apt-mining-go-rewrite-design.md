# APT Mining Platform v4.0 — Go 全栈重写设计文档

> 日期：2026-05-18
> 状态：待实施
> 触发原因：v3.x 累计 82 个阶段补丁后架构复杂度超过可维护上限，性能瓶颈无法通过增量修复解决

---

## 一、技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 后端语言 | Go 1.22+ | 编译为单 .exe 文件部署 |
| Web 框架 | Gin | 最流行的 Go HTTP 框架 |
| 数据库 | PostgreSQL 15+ | 并发读写、并行查询、GIN 索引 |
| 前端框架 | Vue 3 + Element Plus | 保持现有框架，组件拆分 |
| 前端构建 | Vite | 保持现有构建流程 |
| 部署 | 单 .exe + PostgreSQL 服务 | Windows 平台 |

**为什么不用 Python 重构：** 全程 AI 开发导致 82 次迭代后代码复杂度已超过任何人可理解的范围。Python 重构大概率走同样的路。换 Go 强制从头设计，切断补丁惯性。

**为什么用 PostgreSQL 而不是 SQLite：** 导入时写锁阻塞查询、全表扫描无并行引擎、`LIKE '%keyword%'` 全表遍历。PostgreSQL 从根本上解决这些问题。

---

## 二、整体架构

```
浏览器
  │
  ▼
┌─────────────────────────────────────┐
│         PostgreSQL 15+               │
│  ┌──────────────────────────────┐   │
│  │  apt_mining_db (正式)         │   │
│  │  apt_mining_test (测试)       │   │
│  │  15张表 + GIN索引            │   │
│  │  无快照表、无预计算表          │   │
│  └──────────────────────────────┘   │
└──────────────┬──────────────────────┘
               │ lib/pq
               │
┌──────────────▼──────────────────────┐
│       Go 后端 (单 .exe)              │
│  Gin Router → Handler → Service → Repo │
│  静态文件服务 (Vue dist)              │
└──────────────┬──────────────────────┘
               │
               ▼
        Vue 3 SPA (浏览器端)
```

**核心设计原则：**

1. **没有快照表** — 所有查询是实时 SQL，不清缓存、不覆盖数据
2. **单一数据源** — 数据库存什么，API 就返回什么
3. **每个文件 ≤ 400 行** — 路由、服务、模型严格按职责拆分
4. **评分/Badge 在 SQL 中完成** — 不在 Go 里逐行计算

---

## 三、数据库设计

### 3.1 表结构（与现有 SQLite 基本一致）

| 表名 | 说明 | 行数预估 |
|---|---|---|
| `alerts` | 告警行（去重后） | 10w-50w |
| `mined_events` | 事件主表 | < 1000 |
| `mined_event_iocs` | 事件 IOC 关联 | < 5000 |
| `mined_event_devices` | 事件设备关联 | < 5000 |
| `event_followups` | 跟进记录 | < 20000 |
| `tags` | 标签定义 | < 500 |
| `tag_batches` | 标签批次（含设备快照） | < 1000 |
| `device_tags` | 设备标签关联 | < 50000 |
| `traced_targets` | 追踪目标 | < 2000 |
| `imports` | 导入记录（含 file_hash） | < 1000 |
| `import_sheets` | Sheet 信息 | < 5000 |
| `import_rows` | 导入明细 | 10w-50w |
| `audit_log` | 审计日志 | < 100000 |
| `config` | 系统配置 | < 20 |

### 3.2 PostgreSQL 特有索引

```sql
-- GIN 索引：关键词搜索从全表扫描 → 毫秒级
CREATE INDEX idx_alerts_search ON alerts USING gin(
    to_tsvector('simple', COALESCE(device_id,'') || ' ' || COALESCE(source_ip,'') || ' ' || COALESCE(target,''))
);

-- 部分索引：候选查询优化
CREATE INDEX idx_alerts_candidate ON alerts (device_id, target, port, alert_count)
    WHERE threat_type IN ('apt', '远控') OR std_apt_org IS NOT NULL;

-- 事件 IOC 快速匹配
CREATE INDEX idx_event_iocs_lookup ON mined_event_iocs (target, port);

-- 设备标签联合查询
CREATE INDEX idx_device_tags_lookup ON device_tags (device_id, tag_id) WHERE status = 'active';

-- 热度聚合加速
CREATE INDEX idx_alerts_heat_group ON alerts (device_id, target, source_ip);

-- 追踪目标查询
CREATE INDEX idx_traced_target_port ON traced_targets (target, port);
```

### 3.3 候选查询策略（核心改动）

**当前 Python 版的问题：**
- 首次加载 ~14 次 SQL 查询
- Python 逐行装饰（热度/事件/标签/Badge/评分）
- 快照 + 实时覆盖两层数据可能不一致

**Go + PostgreSQL 方案：**
- **1 条 CTE SQL** 搞定全部计算
- PostgreSQL 并行执行器自动并行
- 评分/Badge 用 CASE WHEN 在 SQL 中计算
- Go 只做序列化和分页

```sql
WITH base AS (
    SELECT * FROM alerts
    WHERE first_alert_time >= :date_start AND first_alert_time <= :date_end
      -- 其他筛选条件
),
heat AS (
    SELECT device_id, target,
           COUNT(*) as target_alert_count,
           COUNT(DISTINCT device_id) as target_device_count
    FROM base GROUP BY device_id, target
),
scored AS (
    SELECT a.*,
           -- 评分规则（CASE WHEN）
           CASE WHEN a.threat_type = 'apt' THEN 34 ELSE 0 END +
           CASE WHEN a.std_apt_org IS NOT NULL THEN 26 ELSE 0 END +
           ... as candidate_score,
           -- Badge 计算
           CASE WHEN a.std_apt_org IS NOT NULL THEN 'apt_dict' END as badges
    FROM base a
    LEFT JOIN heat h ON a.device_id = h.device_id AND a.target = h.target
)
SELECT * FROM scored
ORDER BY candidate_score DESC
LIMIT :page_size OFFSET :offset;
```

### 3.4 导入策略

```
POST /api/imports:
  1. 保存文件到 uploads/
  2. goroutine 后台处理:
     a. 流式读取 Excel（excelize OpenReader，逐行不入全表内存）
     b. 每 500 行批量 INSERT（PostgreSQL COPY 协议）
     c. 去重用当前 batch 内 map，不扫全表
     d. 进度写入共享状态（atomic）
  3. 前端轮询 GET /api/imports/{id} 看进度
```

Go goroutine 后台跑，PostgreSQL 读路径独立，导入不阻塞查询。

### 3.5 数据隔离

| 实例 | PostgreSQL 库 | 端口 | 数据目录 |
|---|---|---|---|
| 正式 | `apt_mining_prod` | 8088 | `./data/prod/` |
| 测试 | `apt_mining_test` | 9099 | `./data/test/` |

两个完全独立的 PostgreSQL 数据库，物理隔离，不会串数据。AI 开发时连 `apt_mining_test`。

---

## 四、Go 后端目录结构

```
backend/
├── main.go                     # 入口：Gin 路由 + PostgreSQL + 静态文件
├── go.mod / go.sum             # Go 模块依赖
├── internal/
│   ├── handler/                # HTTP 请求处理（≤ 200 行/文件）
│   │   ├── alert_handler.go
│   │   ├── candidate_handler.go
│   │   ├── event_handler.go
│   │   ├── tag_handler.go
│   │   ├── traced_handler.go
│   │   ├── import_handler.go
│   │   ├── config_handler.go
│   │   ├── device_handler.go
│   │   └── health_handler.go
│   ├── service/                # 业务逻辑（≤ 400 行/文件）
│   │   ├── candidate_service.go   # CTE SQL 构建
│   │   ├── import_service.go      # Excel 流式 + 后台队列
│   │   ├── event_service.go       # 事件 CRUD + IOC 提取
│   │   ├── tag_service.go         # 标签批次 + 批量打标
│   │   ├── badge_engine.go        # Badge 规则引擎
│   │   └── score_engine.go        # 评分规则
│   ├── model/                  # 数据结构体
│   │   ├── alert.go
│   │   ├── event.go
│   │   ├── tag.go
│   │   ├── import.go
│   │   └── config.go
│   ├── repository/             # 数据库操作（≤ 400 行/文件）
│   │   ├── alert_repo.go
│   │   ├── candidate_repo.go    # 候选 CTE 查询
│   │   ├── event_repo.go
│   │   ├── tag_repo.go
│   │   └── import_repo.go
│   └── middleware/             # CORS + Recovery
│       ├── cors.go
│       └── recovery.go
├── migrations/
│   └── 001_initial.up.sql      # 建表 + 索引
│   └── 001_initial.down.sql
├── config/                     # YAML 配置（沿用现有）
├── uploads/                    # 上传暂存
└── static/                     # Vue dist 产物
```

---

## 五、前端组件拆分

```
frontend/src/
├── main.js                     # Vue 3 入口
├── App.vue                     # 应用壳（侧边栏 + 主题切换）
├── router/index.js             # 路由
├── api/                        # HTTP 封装
│   ├── axios.js
│   ├── candidates.js
│   ├── alerts.js
│   ├── events.js
│   ├── tags.js
│   ├── traced.js
│   ├── imports.js
│   └── config.js
├── composables/                # 可复用逻辑
│   ├── useCandidateData.js      # 加载 + 筛选 + 排序 + 分页
│   ├── useColumnConfig.js       # 列配置
│   ├── useColumnFilters.js      # 表头筛选
│   ├── useTheme.js              # 主题切换
│   └── useTableResize.js        # 列宽拖拽
├── components/                 # 通用组件
│   ├── SortButton.vue
│   ├── ColumnHeaderFilter.vue
│   ├── ResizableTable.vue
│   └── LoadingProgress.vue
└── views/
    ├── Workbench.vue            # 壳 < 200 行
    ├── Events.vue               # 壳 < 200 行
    ├── Alerts.vue               # 壳 < 200 行
    ├── Settings.vue             # 壳 < 300 行
    ├── workbench/
    │   ├── FilterBar.vue
    │   ├── CandidateTable.vue
    │   ├── CreateEventDialog.vue
    │   └── ActionButtons.vue
    ├── events/
    │   ├── EventList.vue
    │   ├── EventDetail.vue
    │   ├── EventFormDialog.vue
    │   ├── FollowupTimeline.vue
    │   └── IocManager.vue
    └── settings/
        ├── ImportTab.vue
        ├── TagsTab.vue
        ├── TracedTab.vue
        ├── ConfigTab.vue
        └── SystemInfoTab.vue
```

**拆分原则：** 每个页面壳 < 300 行，子组件 < 500 行，逻辑抽 composables。

---

## 六、API 对照表

### 6.1 保留的端点（逻辑不变）

| 方法 | 路径 | Python 源文件 | Go 目标文件 |
|---|---|---|---|
| GET | `/api/health` | main.py | health_handler.go |
| GET | `/api/version` | version.py | health_handler.go |
| GET | `/api/alerts` | alerts.py | alert_handler.go |
| GET | `/api/alerts/options` | alerts.py | alert_handler.go |
| POST | `/api/alerts/export` | alerts.py | alert_handler.go |
| GET | `/api/alert-candidates` | alerts.py | candidate_handler.go |
| GET | `/api/events` | events.py | event_handler.go |
| POST | `/api/events` | events.py | event_handler.go |
| GET | `/api/events/{id}` | events.py | event_handler.go |
| PATCH | `/api/events/{id}` | events.py | event_handler.go |
| DELETE | `/api/events/{id}` | events.py | event_handler.go |
| POST | `/api/events/{id}/followups` | events.py | event_handler.go |
| POST | `/api/events/{id}/devices` | events.py | event_handler.go |
| POST | `/api/events/{id}/iocs` | events.py | event_handler.go |
| DELETE | `/api/events/{id}/devices/{device_id}` | events.py | event_handler.go |
| DELETE | `/api/events/{id}/iocs` | events.py | event_handler.go |
| GET | `/api/tags` | tags.py | tag_handler.go |
| GET | `/api/tags/batches` | tags.py | tag_handler.go |
| POST | `/api/tags/batches` | tags.py | tag_handler.go |
| POST | `/api/tags/batches/import-text-files` | tags.py | tag_handler.go |
| DELETE | `/api/tags/batches/{id}` | tags.py | tag_handler.go |
| GET | `/api/tags/devices/{device_id}/tags` | tags.py | tag_handler.go |
| POST | `/api/tags/devices/tags` | tags.py | tag_handler.go |
| DELETE | `/api/tags/devices/{device_id}/tags/{tag_id}` | tags.py | tag_handler.go |
| GET | `/api/traced` | traced.py | traced_handler.go |
| POST | `/api/traced` | traced.py | traced_handler.go |
| POST | `/api/traced/import` | traced.py | traced_handler.go |
| PATCH | `/api/traced/{id}` | traced.py | traced_handler.go |
| DELETE | `/api/traced/{id}` | traced.py | traced_handler.go |
| POST | `/api/imports` | imports.py | import_handler.go |
| GET | `/api/imports` | imports.py | import_handler.go |
| GET | `/api/imports/{id}` | imports.py | import_handler.go |
| GET | `/api/imports/{id}/sheets` | imports.py | import_handler.go |
| GET | `/api/imports/{id}/rows` | imports.py | import_handler.go |
| GET | `/api/imports/{id}/failures.csv` | imports.py | import_handler.go |
| DELETE | `/api/imports/{id}` | imports.py | import_handler.go |
| GET | `/api/devices` | devices.py | device_handler.go |
| GET | `/api/config` | config.py | config_handler.go |
| POST | `/api/config` | config.py | config_handler.go |
| POST | `/api/config/reload` | config.py | config_handler.go |
| GET | `/api/config/dicts` | config.py | config_handler.go |
| GET | `/api/persistence` | persistence.py | health_handler.go |

### 6.2 删除的代码（不再需要）

| 文件 | 行数 | 原因 |
|---|---|---|
| `snapshot_builder.py` | 1246 | 快照预计算（CTE SQL 替代） |
| `alerts.py` 快照路径 | ~800 | `_query_from_snapshot`、`_build_snapshot_filter_options` |
| `alerts.py` 缓存管理 | ~400 | `_candidate_cache`、`_full_cache`、`sorted_views` |
| `alerts.py` 实时覆盖层 | ~200 | `_refresh_live_relations` |
| 所有 `patch_snapshot_for_*` | ~300 | 散落在 events.py/tags.py/traced.py |
| **合计** | **~2946 行** | |

### 6.3 保留的核心业务逻辑

- 评分规则表（`RULE_SCORE_MAP`）→ `score_engine.go`
- Badge 判断引擎（9 种 badge）→ `badge_engine.go`
- IOC 提取逻辑（`extract_iocs_from_text`）→ `event_service.go`
- Excel 解析字段映射 → `import_service.go`
- 去重策略（content_hash）→ `import_service.go`

---

## 七、实施计划

### 阶段 1：基础搭建（第 1 周）
- 安装 Go + PostgreSQL
- 初始化 Go 模块、Gin 项目结构
- 数据库迁移脚本（建表 + 索引）
- 健康检查接口
- 配置加载（YAML）

### 阶段 2：核心查询引擎（第 2-3 周）
- 候选查询 CTE SQL 构建
- 评分/Badge 计算（CASE WHEN）
- 告警列表 + 筛选选项
- Excel 流式导入（goroutine 后台处理）
- 前端候选页对接新后端

### 阶段 3：事件与标签（第 4-5 周）
- 事件 CRUD + IOC 提取
- 标签批次 + 批量打标
- 追踪库管理
- 前端组件拆分（Workbench → 5 个子组件）

### 阶段 4：打磨与切换（第 6-7 周）
- 配置管理 + 词典加载
- 导出功能（CSV/Excel）
- 设备列表
- 数据迁移工具（SQLite → PostgreSQL）
- 完整回归测试
- 旧 Python 后端停用

---

## 八、预期效果

| 指标 | 当前（v3.x） | 重写后（v4.0） |
|---|---|---|
| 候选页加载 | 首次 ~110s，后续依赖缓存 | ≤ 3s（CTE SQL） |
| 上传 10 万行 | 经常卡死其他请求 | 后台处理，不阻塞查询 |
| 创建事件后可见性 | 可能不可见（快照未 patch） | 即时可见（实时查询） |
| 修一个 bug 的风险 | 高（牵一发动全身） | 低（模块隔离） |
| 单文件最大行数 | 2426 行 | ≤ 400 行 |
| 总代码行数 | ~18,000 | ~10,000（精简 45%） |

---

## 九、风险与缓解

| 风险 | 概率 | 缓解措施 |
|---|---|---|
| Go 学习曲线 | 中 | 有人愿意学，Go 语法简单 |
| PostgreSQL 安装 | 低 | Windows 图形安装向导，5 分钟完成 |
| 业务逻辑遗漏 | 中 | 逐条 API 对照 + 回归测试 |
| 前端兼容 | 低 | API 响应格式保持不变 |
