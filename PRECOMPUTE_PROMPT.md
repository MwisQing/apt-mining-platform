# 研判工作台预计算方案开发提示词

> 将本文件完整内容作为提示词发给 AI 助手，让它按照设计文档实现预计算方案。

---

## 你的任务

你需要为 APT Mining Workbench（APT 挖掘工作台）实现 **研判工作台预计算方案**，将当前"请求时全量计算"的架构改为"导入时预计算 + 请求时查表 + 变更时增量更新"。

先阅读项目根目录下的 `CLAUDE.md` 了解项目背景、API 清单和目录结构，再阅读 `PRECOMPUTE_DESIGN_v3.md` 了解完整设计方案。

---

## 背景

研判工作台 `/api/alert-candidates` 接口当前在每次请求时对约 92,000 行候选数据执行 Python 层全量装饰（badge 计算、评分、事件/IOC/标签关联、热度查询、摘要生成），首次请求耗时 80-110 秒。SQL 查询本身只需 2-6 秒，瓶颈在 Python 循环。

之前做过进程内缓存（`_full_cache`/`_candidate_cache`）只对"换日期"有效，换其他筛选条件仍要全量重算。也做过快照表基础设施但未接入主查询路径就被放弃了（因为只有全量重建没有增量更新）。

---

## 你需要做的事情（按顺序）

### 第一步：阅读现有代码

必须完整阅读以下文件，理解现有实现：

1. `CLAUDE.md` — 项目全貌（API 清单、表结构、前端约定）
2. `PRECOMPUTE_DESIGN_v3.md` — **完整设计文档**，你的实现必须严格遵循此文档
3. `backend/api/alerts.py` — 当前候选查询和装饰全链路（核心文件，约 1900 行）
   - 重点：`_make_items`、`_decorate_candidate_items`、`_query_all_candidate_items`、`_query_candidate_items`、`query_alert_candidates`（GET 端点）
   - 重点：`_build_where`（筛选条件构建）、`_heat_and_source_maps`、`_cross_day_and_lateral`
   - 重点：`_event_maps_for_rows`、`_trace_maps_for_rows`、`_device_tag_map_for_rows`
   - 重点：`_build_filter_options`（筛选选项构建）
4. `backend/services/alert_workbench.py` — 候选规则、评分公式、优先级分类
   - 重点：`DEFAULT_CANDIDATE_RULES`、`detect_candidate_matches`、`compute_candidate_score`、`build_candidate_reason_labels`、`classify_candidate_priority`
5. `backend/services/__init__.py` — `compute_badges` 函数（badge 计算逻辑）
6. `backend/services/snapshot_builder.py` — 现有快照构建器（需要重写）
7. `backend/models/snapshot.py` — 现有快照表模型（需要小改）
8. `backend/api/events.py` — 事件 CRUD 接口（需要接入增量更新）
9. `backend/api/traced.py` — IOC 备注接口（需要接入增量更新）
10. `backend/api/tags.py` — 标签接口（需要接入增量更新）
11. `backend/api/imports.py` — 导入接口（需要接入全量重建触发）
12. `backend/utils/db.py` — 数据库初始化和自动迁移（需要添加新字段/索引）
13. `frontend/src/views/Workbench.vue` — 前端工作台（确认不需要改动或只做极小调整）

### 第二步：实现全量构建

改造 `backend/services/snapshot_builder.py`：

1. 重写 `rebuild_candidate_snapshots` 函数：
   - 复用现有 `alerts.py` 中的 `_query_all_candidate_items` 获取装饰好的全量数据
   - 写入快照表时，额外写入 `badges_json`、`device_tags_json`、`device_event_json` 三个新列
   - `badges_json`：将 item["badges"] 序列化为 JSON 字符串
   - `device_tags_json`：将 item["device_tags"] 序列化为 JSON 字符串
   - `device_event_json`：将 item["device_event"] 序列化为 JSON 字符串
   - 保留 badge/tag 子表写入（用于结构化筛选）
   - 添加旧版本清理：全量构建成功后，删除除最近 2 个 version 外的旧数据

2. 现有的 `_snapshot_row_from_candidate` 函数需要更新，添加新字段

3. 保留 `rebuild_candidate_snapshots_async` 异步入口

### 第三步：实现增量更新函数

在 `backend/services/snapshot_builder.py` 中新增：

1. `patch_snapshot_for_event(db, event_id)` — 事件变更后增量更新
   - 获取事件关联的 IOC 和设备列表
   - 找到快照中受影响的行（通过 target+port 和 device_id）
   - 重新加载最新的事件映射
   - 对受影响行重算 event_json、device_event_json、score、priority、reasons、badges
   - UPDATE 快照表
   - 同步更新 badge/tag 子表

2. `patch_snapshot_for_trace(db, target, port)` — IOC 备注变更后增量更新
   - 找到快照中 target+port 匹配的行
   - 重新加载最新的追踪信息
   - 对受影响行重算 trace_json、trace_status、ioc_note、score、priority、reasons、badges
   - UPDATE 快照表

3. `patch_snapshot_for_device_tags(db, device_ids)` — 设备标签变更后增量更新
   - 找到快照中 device_id 匹配的行
   - 重新加载最新的设备标签
   - 对受影响行重算 device_tags_json、device_note_summary、score、priority、reasons、badges
   - UPDATE 快照表
   - 同步更新 tag 子表

4. 辅助函数：
   - `_recompute_score(snap_row, event_info=, trace_info=, device_tags=)` — 从快照静态字段 + 最新动态数据重算评分
   - `_recompute_reasons(snap_row, event_info=, trace_info=, device_tags=)` — 重算命中原因
   - `_recompute_badges_json(snap_row, event_info=, trace_info=, device_tags=)` — 重算 badges
   - `_load_snapshot_row(db, snap_id)` — 加载一行快照数据
   - `_sync_badge_subtable(db, version, affected_ids)` — 同步 badge 子表
   - `_sync_tag_subtable(db, version, device_id, tags)` — 同步 tag 子表

**重算 score 的关键逻辑**（必须与 `alert_workbench.py` 中 `compute_candidate_score` 完全一致）：

```
score = 规则命中分（从 candidate_rule_ids_json 反查）
      + 威胁等级分（从 threat_level 列）
      + APT分级分（从 apt_org_tier 列）
      + 热度分（从 heat_* 列，已预存）
      + 厂商分（从 vendors 列）
      + 追踪减分（从传入的 trace_info 或快照已有值）
      + 事件加分（从传入的 event_info 或快照已有值）
      + 标签加分（从传入的 device_tags 或快照已有值）
```

规则命中分的反查映射：
```python
RULE_SCORE_MAP = {
    "threat_type_apt": 34,
    "threat_type_remote_control": 30,
    "std_apt_org_present": 26,
    "apt_org_present": 22,
    "intel_tags_c2_remote": 18,
}
```

### 第四步：改造查询路径

改造 `backend/api/alerts.py` 中的 `query_alert_candidates` 端点：

1. 检查 `get_active_snapshot_version(db)`
2. 有 active version → 走新的 `_query_from_snapshot` 函数
3. 无 active version → 走旧实时路径（兜底）

实现 `_query_from_snapshot`（详见设计文档第 6.2 节）：
- 构建 WHERE 子句（映射所有筛选参数到快照表字段）
- 构建 ORDER BY（映射所有排序字段到快照表列）
- 执行 COUNT + 分页 SELECT
- 用 `_snapshot_row_to_response` 组装返回
- 用 `_build_snapshot_filter_options_v3` 获取筛选选项

注意事项：
- `device_tags` 筛选通过 `alert_candidate_snapshot_tags` 子表 EXISTS 子查询
- `exclude_device_tags` 排除通过 NOT EXISTS 子查询
- `badges_filter` 通过 `alert_candidate_snapshot_badges` 子表 EXISTS 子查询
- `hide_traced` 通过 `s.trace_status != 'active'`
- `hide_closed` 通过 `COALESCE(s.event_status, '') != 'closed'`
- 排序字段直接映射到快照表列（所有字段都已预计算存储）

### 第五步：接入变更触发点

详见设计文档第 7 节的完整清单。关键文件：

**`backend/api/events.py`**：
- 所有事件变更接口（创建、修改、删除、添加/移除IOC、添加/移除设备）在 `db.commit()` 后调用 `patch_snapshot_for_event(db, event_id)`
- 删除事件和移除 IOC 时，需要在删除前保存 IOC/设备列表
- 替换现有的 `_invalidate_candidate_cache()` 调用

**`backend/api/traced.py`**：
- 添加/修改/删除 IOC 备注后调用 `patch_snapshot_for_trace(db, target, port)`
- 批量导入 IOC 后对每个唯一 (target, port) 调用

**`backend/api/tags.py`**：
- 所有标签变更接口后调用 `patch_snapshot_for_device_tags(db, affected_device_ids)`
- 替换现有的 `_invalidate_candidate_cache()` 调用

**`backend/api/imports.py`**：
- 导入完成后触发 `rebuild_candidate_snapshots_async()`（已有类似逻辑，确认正确接入）

### 第六步：数据库迁移

在 `backend/utils/db.py` 的 `_ensure_runtime_schema` 中添加：

```python
# 新增快照表字段
_safe_add_column(conn, "alert_candidate_snapshots", "badges_json", "TEXT DEFAULT '[]'")
_safe_add_column(conn, "alert_candidate_snapshots", "device_tags_json", "TEXT DEFAULT '[]'")
_safe_add_column(conn, "alert_candidate_snapshots", "device_event_json", "TEXT")

# 新增索引
_safe_create_index(conn, "idx_snap_target_port", "alert_candidate_snapshots", ["snapshot_version", "target", "port"])
_safe_create_index(conn, "idx_snap_device_id", "alert_candidate_snapshots", ["snapshot_version", "device_id"])
_safe_create_index(conn, "idx_snap_date_range", "alert_candidate_snapshots", ["snapshot_version", "first_alert_time", "last_alert_time"])
_safe_create_index(conn, "idx_snap_score_desc", "alert_candidate_snapshots", ["snapshot_version", "candidate_score DESC"])
```

同步更新 `backend/models/snapshot.py` 的 `AlertCandidateSnapshot` 类，添加三个新 Column。

### 第七步：编写测试

在 `backend/tests/` 目录下新增测试文件 `test_snapshot_precompute.py`：

1. **全量构建测试**：
   - 插入测试告警 → 全量构建 → 验证快照行数、字段正确性
   - 验证 badge/tag 子表数据
   - 验证 active_version 已切换

2. **增量更新测试**：
   - 全量构建后创建事件 → 验证受影响行的 event_json/score 更新
   - 全量构建后添加 IOC 备注 → 验证受影响行的 trace_status/ioc_note/score 更新
   - 全量构建后打设备标签 → 验证受影响行的 device_tags_json/score 更新

3. **查询路径测试**：
   - 全量构建后 GET /api/alert-candidates → 验证返回 snapshot_status="snapshot"
   - 测试日期筛选、关键词搜索、排序
   - 测试 badges_filter、device_tags 筛选

4. **一致性测试**：
   - 对同一数据集，对比快照路径和旧实时路径的返回结果
   - 验证 score、priority、badges 完全一致

### 第八步：验证

1. 运行所有后端测试：`python -m unittest discover backend/tests`
2. 运行前端构建：`cd frontend && npm run build`
3. 手动测试：
   - 导入 Excel → 等待快照构建完成
   - 选择日期 → 确认 <1 秒返回
   - 创建事件 → 返回工作台确认事件显示正确
   - 添加 IOC 备注 → 返回工作台确认备注显示正确
   - 打设备标签 → 返回工作台确认标签显示正确

---

## 关键约束

1. **不要改后端 API 的请求/响应格式**。前端 Workbench.vue 依赖当前的 JSON 结构（items 数组中每个 item 的字段名和嵌套结构），快照路径返回的数据必须与旧实时路径格式完全一致。

2. **保留旧实时路径作为兜底**。当 `active_version` 为空时（无快照），走旧的 `_query_candidate_items` + `_decorate_candidate_items` 路径。不要删除旧代码。

3. **增量更新必须同步执行**（在 API 请求的事务中），不能用后台线程。这保证了用户创建事件后刷新工作台能立即看到更新。只有全量重建可以异步。

4. **评分公式必须与现有完全一致**。`_recompute_score` 的结果必须与 `compute_candidate_score` 对同样输入的结果相同。这是最容易出错的地方，务必对照 `alert_workbench.py` 中的公式逐项实现。

5. **badge 计算必须与现有完全一致**。增量更新重算 badges 时，必须复用 `compute_badges` + `_build_relation_badges` 的逻辑，不能简化或遗漏。

6. **SQLite 兼容**。所有 SQL 必须兼容 SQLite 语法。不能使用 PostgreSQL/MySQL 特有语法。

7. **前端尽量不改**。如果必须改，只做极小调整（如增加 snapshot_status 判断），不要改变数据加载和展示的主流程。

---

## 项目技术栈

- 后端：FastAPI + SQLAlchemy + SQLite（WAL 模式）
- 前端：Vue 3 (Composition API) + Vite + Element Plus + JavaScript
- 语言：Python 后端，JavaScript 前端（不用 TypeScript）
- 运行方式：本地单机，`http://127.0.0.1:8088`

---

## 验收标准

1. 选择日期后加载候选数据 **< 1 秒**（目标 < 0.3 秒）
2. 创建事件/添加 IOC 备注/打标签后，返回工作台数据正确更新，**< 1 秒**
3. 导入 Excel 后全量构建在后台异步完成，**不阻塞用户操作**
4. 所有现有筛选条件（日期、关键词、设备标签、排除标签、威胁类型、APT 分级、target_kind、badges_filter、hide_traced）**全部正常工作**
5. 排序功能（评分、时间、告警次数、热度等）**全部正常工作**
6. 后端测试全部通过
7. 前端 `npm run build` 通过
