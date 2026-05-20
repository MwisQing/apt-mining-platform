# 研判工作台候选快照表技术方案 v2

日期：2026-05-11

适用范围：APT Mining Platform v3.1.4+

状态：可进入开发评估

关联文档：

- [WORKBENCH_PERFORMANCE_ANALYSIS_2026-05-11.md](C:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-3.1.4\apt-mining-platform-3.1.4\WORKBENCH_PERFORMANCE_ANALYSIS_2026-05-11.md)
- [SNAPSHOT_TABLE_DESIGN.md](C:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-3.1.4\apt-mining-platform-3.1.4\SNAPSHOT_TABLE_DESIGN.md)
- [SNAPSHOT_TABLE_DESIGN_REVIEW_2026-05-11.md](C:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-3.1.4\apt-mining-platform-3.1.4\SNAPSHOT_TABLE_DESIGN_REVIEW_2026-05-11.md)

---

## 1. 目标

将研判工作台 `/api/alert-candidates` 从当前的“请求期全量 Python 计算”改为“后台预计算 + 请求期查快照”，实现：

- 首次打开工作台显著提速
- 日期、目标类型、标签、威胁类型、追踪状态等筛选都接近秒级
- 查询语义稳定
- 构建和刷新过程对前台读请求透明

性能目标建议：

- 首次打开工作台：`< 3s`
- 切换日期：`< 1s`
- 切换顶部筛选条件：`< 1s`
- 翻页 / 排序：`< 1s`

---

## 2. 背景与根因

现状瓶颈已经确认：

- SQL 去重和聚合不是主瓶颈
- 主瓶颈在 `backend/api/alerts.py` 的 `_make_items` 与 `_decorate_candidate_items`
- 当前会对 9 万多条候选结果逐条执行：
  - badge 计算
  - 事件 / 追踪 / 标签关系匹配
  - 评分计算
  - 原因摘要拼接
  - 排序辅助字段构造

结论：

**当前性能问题的根因是“请求期全量计算”，不是 FastAPI 本身慢，也不是单纯索引不够。**

---

## 3. v2 核心原则

v2 方案遵循以下原则：

1. 请求期不再做全量候选装饰
2. 快照重建不能暴露空表或半成品
3. badge / tag 过滤必须是结构化过滤，不允许 JSON `LIKE`
4. 前端契约必须明确，不能口头说“前端不用改”
5. 全量重建和增量刷新必须有一致性模型

---

## 4. 总体架构

### 4.1 改造前

```text
用户请求
  -> SQL 去重取候选
  -> Python 逐条装饰
  -> 内存缓存
  -> 过滤 / 排序 / 分页
  -> 返回
```

### 4.2 改造后

```text
导入完成 / 数据变更
  -> 后台任务构建快照版本
  -> 构建完成后原子切换 active version

用户请求
  -> 查询 active snapshot version
  -> WHERE + ORDER BY + LIMIT
  -> 轻量 JSON 反序列化
  -> 返回
```

### 4.3 版本模型

v2 不直接覆盖正式快照数据，采用版本切换。

关键概念：

- `active_snapshot_version`
- `building_snapshot_version`

读请求规则：

- 只读取 `active_snapshot_version`

构建规则：

- 所有新快照先写入 `building_snapshot_version`
- 校验通过后切换为 `active_snapshot_version`
- 旧版本保留一段时间后清理

这样可避免：

- 重建期间空表
- 半成品被读到
- 增量任务覆盖新版本

---

## 5. 数据库设计

## 5.1 主表 `alert_candidate_snapshots`

主表只存“单条候选”的主状态和查询主字段。

```sql
CREATE TABLE IF NOT EXISTS alert_candidate_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_version TEXT NOT NULL,

    device_id TEXT NOT NULL,
    target TEXT NOT NULL,
    port TEXT NOT NULL DEFAULT '',

    source_ip TEXT,
    source_ips TEXT,
    source_ip_count INTEGER DEFAULT 0,

    target_type TEXT,
    target_kind TEXT,
    target_kind_label TEXT,

    threat_type TEXT,
    threat_level TEXT,
    std_apt_org TEXT,
    apt_org TEXT,
    apt_org_tier TEXT,
    vendors TEXT,
    protocol TEXT,
    intel_tags TEXT,
    dns_resolved_ip TEXT,
    asset_type TEXT,

    analysis_status TEXT DEFAULT '',
    is_focused INTEGER DEFAULT 0,

    alert_count INTEGER DEFAULT 0,
    first_alert_time TEXT,
    last_alert_time TEXT,

    heat_target_alert_count INTEGER DEFAULT 0,
    heat_target_device_count INTEGER DEFAULT 0,
    heat_device_alert_count INTEGER DEFAULT 0,
    heat_device_target_count INTEGER DEFAULT 0,
    heat_source_ip_alert_count INTEGER DEFAULT 0,

    candidate_score INTEGER DEFAULT 0,
    candidate_priority TEXT,
    candidate_priority_label TEXT,
    candidate_rule_ids_json TEXT,
    candidate_reasons_json TEXT,

    event_json TEXT,
    event_status TEXT,
    trace_json TEXT,
    trace_status TEXT,
    ioc_note TEXT,

    cross_day INTEGER DEFAULT 0,
    lateral INTEGER DEFAULT 0,

    heat_summary_json TEXT,
    relation_summary TEXT,
    candidate_summary TEXT,
    candidate_focus TEXT,
    device_note_summary TEXT,

    sort_priority_rank INTEGER DEFAULT 0,
    sort_rule_hits INTEGER DEFAULT 0,
    sort_target_device_count INTEGER DEFAULT 0,
    sort_target_alert_count INTEGER DEFAULT 0,
    sort_source_ip_alert_count INTEGER DEFAULT 0,
    sort_trace_status TEXT,
    sort_event_status TEXT,

    updated_at TEXT NOT NULL,

    UNIQUE(snapshot_version, device_id, target, port)
);
```

## 5.2 子表 `alert_candidate_snapshot_badges`

用于结构化 badge 过滤。

```sql
CREATE TABLE IF NOT EXISTS alert_candidate_snapshot_badges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_version TEXT NOT NULL,
    snapshot_id INTEGER NOT NULL,
    badge_name TEXT NOT NULL,
    badge_label TEXT NOT NULL,
    badge_color TEXT,
    FOREIGN KEY(snapshot_id) REFERENCES alert_candidate_snapshots(id) ON DELETE CASCADE
);
```

## 5.3 子表 `alert_candidate_snapshot_tags`

用于结构化标签过滤与 `filter_options` 聚合。

```sql
CREATE TABLE IF NOT EXISTS alert_candidate_snapshot_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_version TEXT NOT NULL,
    snapshot_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    tag_name TEXT NOT NULL,
    tag_color TEXT,
    FOREIGN KEY(snapshot_id) REFERENCES alert_candidate_snapshots(id) ON DELETE CASCADE
);
```

## 5.4 元数据表 `snapshot_build_meta`

用于管理版本和构建状态。

```sql
CREATE TABLE IF NOT EXISTS snapshot_build_meta (
    snapshot_type TEXT PRIMARY KEY,
    active_version TEXT,
    building_version TEXT,
    status TEXT NOT NULL DEFAULT 'idle',
    last_built_at TEXT,
    last_build_started_at TEXT,
    last_build_duration_ms INTEGER DEFAULT 0,
    last_row_count INTEGER DEFAULT 0,
    last_error TEXT
);
```

说明：

- 当前 `snapshot_type` 固定可用 `alert_candidates`
- 后续如果有别的快照类型，可复用该表

---

## 6. 索引设计

```sql
CREATE INDEX IF NOT EXISTS idx_snap_version_first_time
ON alert_candidate_snapshots(snapshot_version, first_alert_time);

CREATE INDEX IF NOT EXISTS idx_snap_version_score
ON alert_candidate_snapshots(snapshot_version, candidate_score DESC);

CREATE INDEX IF NOT EXISTS idx_snap_version_target_type
ON alert_candidate_snapshots(snapshot_version, target_type);

CREATE INDEX IF NOT EXISTS idx_snap_version_threat_type
ON alert_candidate_snapshots(snapshot_version, threat_type);

CREATE INDEX IF NOT EXISTS idx_snap_version_threat_level
ON alert_candidate_snapshots(snapshot_version, threat_level);

CREATE INDEX IF NOT EXISTS idx_snap_version_apt_tier
ON alert_candidate_snapshots(snapshot_version, apt_org_tier);

CREATE INDEX IF NOT EXISTS idx_snap_version_trace
ON alert_candidate_snapshots(snapshot_version, trace_status);

CREATE INDEX IF NOT EXISTS idx_snap_version_priority
ON alert_candidate_snapshots(snapshot_version, candidate_priority);

CREATE INDEX IF NOT EXISTS idx_snap_version_target
ON alert_candidate_snapshots(snapshot_version, target);

CREATE INDEX IF NOT EXISTS idx_snap_badges_version_name
ON alert_candidate_snapshot_badges(snapshot_version, badge_name);

CREATE INDEX IF NOT EXISTS idx_snap_tags_version_tag
ON alert_candidate_snapshot_tags(snapshot_version, tag_id);

CREATE INDEX IF NOT EXISTS idx_snap_tags_version_name
ON alert_candidate_snapshot_tags(snapshot_version, tag_name);
```

---

## 7. 快照构建方案

## 7.1 文件建议

新增文件：

- `backend/services/snapshot_builder.py`

职责：

- 全量构建快照版本
- 增量刷新快照
- 元数据状态管理
- 构建锁 / 单飞机制

## 7.2 全量构建流程

```text
1. 申请构建锁
2. 生成 new_version
3. 更新 snapshot_build_meta.status = building
4. 删除 new_version 的残留数据
5. 读取 alerts 去重结果
6. 计算候选主表行
7. 批量写入主表
8. 批量写入 badges 子表
9. 批量写入 tags 子表
10. 校验行数 / 抽样校验
11. 原子切换 active_version = new_version
12. 清理旧版本
13. 更新 status = ready
14. 释放构建锁
```

## 7.3 构建中的数据隔离

禁止以下做法：

- `DELETE FROM 正式表`
- 边写边读同一个版本
- `INSERT OR REPLACE` 直接打到活跃版本

允许的做法：

- 构建版本与活跃版本隔离
- 读请求只查活跃版本

## 7.4 推荐的版本号格式

建议：

- `candidate_20260511_173012_abc123`

来源可包括：

- 时间戳
- 构建触发类型
- 短随机串

---

## 8. 查询接口设计

## 8.1 `/api/alert-candidates` 行为

请求期只做：

- 获取当前 `active_version`
- 基于主表和结构化子表做筛选
- SQL 排序
- SQL 分页
- 反序列化必要 JSON 字段

## 8.2 筛选设计

### 主表内可直接过滤的字段

- `date_start/date_end`
- `target_type`
- `target_kind`
- `threat_types`
- `threat_levels`
- `apt_tiers`
- `hide_traced`
- `hide_closed`
- `alert_count_max`
- `keyword`

### 通过子表过滤的字段

- `device_tags`
- `exclude_device_tags`
- `badges_filter`

### badge 过滤方式

使用 `EXISTS` 结构化子查询：

```sql
EXISTS (
  SELECT 1
  FROM alert_candidate_snapshot_badges b
  WHERE b.snapshot_id = s.id
    AND b.snapshot_version = s.snapshot_version
    AND b.badge_name = :badge_name
)
```

禁止：

- `badges_json LIKE`

### 设备标签过滤方式

使用 `EXISTS / NOT EXISTS` 对 `alert_candidate_snapshot_tags` 过滤。

这样可以：

- 精确匹配
- 利用索引
- 与主表解耦

---

## 9. `filter_options` 契约

v2 明确规定：

**后端继续完整提供 `filter_options`。**

不允许：

- `device_tags` 留空后让前端从当前页提取
- `badges` 留空后让前端兜底

理由：

- 当前前端工作台已经依赖后端 `filter_options`
- 如果后端不完整提供，会造成行为退化

## 9.1 推荐聚合来源

- `threat_type`：主表 `DISTINCT`
- `std_apt_org`：主表 `DISTINCT`
- `port`：主表 `DISTINCT`
- `device_tags`：子表 `DISTINCT tag_name`
- `badges`：子表 `DISTINCT badge_label`
- `priority`：固定值 `高优先/中优先/观察`
- `ioc_note`：仍为文本输入，不提供枚举

## 9.2 `filter_options` 是否缓存

可做短 TTL 缓存，但必须按 `active_version` 维度缓存。

也就是说：

- 版本切换后必须失效

---

## 10. 前端契约

## 10.1 前端是否需要修改

v2 结论：

- 主列表字段结构应保持兼容
- 但前端**需要最小修改**以正确处理“快照构建中”状态

所以不能再写“前端完全不需要改”。

## 10.2 新的响应约定

当快照可用时：

```json
{
  "items": [...],
  "total": 123,
  "page": 1,
  "page_size": 50,
  "meta": {
    "snapshot_status": "ready"
  },
  "filter_options": {...}
}
```

当快照构建中且尚无活跃版本时：

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 50,
  "meta": {
    "snapshot_status": "building",
    "message": "候选快照正在构建中，请稍候..."
  },
  "filter_options": {
    "device_tags": [],
    "threat_type": [],
    "std_apt_org": [],
    "priority": ["高优先", "中优先", "观察"],
    "port": [],
    "badges": [],
    "ioc_note": null
  }
}
```

## 10.3 前端建议行为

工作台前端应增加：

- 当 `meta.snapshot_status === "building"` 时展示“构建中”提示
- 可选轮询 `GET /api/snapshots/status`
- 不把“空表”误认为“没有数据”

---

## 11. 刷新触发点

## 11.1 全量重建触发点

- Excel 导入完成后
- 配置影响评分 / badge 规则后
- 管理员手动触发

## 11.2 增量刷新触发点

- 标签变更
- 追踪变更
- 事件 IOC 变更

---

## 12. 一致性模型

这是 v2 的关键补充。

## 12.1 单飞机制

同一时间只允许一个全量构建任务进行。

如果新的全量构建请求到来：

- 若当前已有全量构建在执行，则只记录“待重建”标记
- 当前任务完成后再补跑一次

## 12.2 增量刷新队列

建议引入内存队列或任务表，按以下粒度合并：

- 标签：按 `device_id`
- 追踪：按 `(target, port?)`
- 事件：按 `target`

避免短时间内重复刷新同一对象。

## 12.3 版本隔离

规则如下：

- 全量构建只写 `building_version`
- 增量刷新默认只作用于 `active_version`
- 如果正在全量构建，则增量事件记入 dirty queue
- 全量构建完成后，再对新版本应用积压的增量刷新

这样可以避免：

- 新版本刚切换就被旧任务覆盖
- 新旧版本数据混杂

## 12.4 失败恢复

如果构建失败：

- 保持旧 `active_version` 不变
- `snapshot_build_meta.status = error`
- 记录 `last_error`
- 前台仍继续读旧版本

禁止：

- 构建失败后把活跃版本置空

---

## 13. 启动与空快照处理

## 13.1 启动行为

启动时检查：

- 是否存在 `active_version`

如果没有：

- 异步触发首次全量构建

## 13.2 空快照策略

如果系统从未构建成功过：

- `/api/alert-candidates` 返回 `snapshot_status=building`
- 前端展示构建中提示

如果已有旧版本而新版本正在构建：

- 继续返回旧版本数据
- `meta.snapshot_status` 可返回 `ready`，并可附加 `rebuilding=true`

---

## 14. 回滚方案

v2 必须支持安全回滚。

## 14.1 代码回滚

只需将 `/api/alert-candidates` 恢复为旧实现。

## 14.2 数据回滚

快照表是附加结构：

- 不影响原始 `alerts`
- 可保留快照表不启用
- 必要时可直接删除快照相关表

## 14.3 运行时回滚

如果快照接口出现问题：

- 保留旧候选查询实现作为 feature flag fallback
- 通过配置切回旧链路

建议增加：

- `config.yaml` 中的 `use_snapshot_candidates: true/false`

---

## 15. 实施顺序

### 第一阶段

- 建表
- 元数据表
- 主表与子表索引

### 第二阶段

- `snapshot_builder.py`
- 全量构建
- 版本切换
- 构建状态接口

### 第三阶段

- 改写 `/api/alert-candidates`
- 接入 `filter_options`
- 增加 feature flag

### 第四阶段

- 导入后触发全量构建
- 标签 / 追踪 / 事件增量刷新
- 队列与合并逻辑

### 第五阶段

- 前端构建中态
- 回归测试
- 性能压测

---

## 16. 测试建议

## 16.1 正确性测试

同一批数据下，对比：

- 老接口结果
- 新快照接口结果

至少对比：

- `candidate_score`
- `candidate_priority`
- `badges`
- `device_tags`
- `trace_status`
- `event_status`
- `candidate_reasons`

## 16.2 性能测试

要求覆盖：

- 首次打开
- 改日期
- 改目标类型
- 改标签
- 改威胁类型
- 改隐藏已追踪
- 翻页
- 排序

## 16.3 并发测试

必须覆盖：

- 全量构建时读请求并发
- 全量构建与标签增量刷新并发
- 全量构建失败恢复
- 连续导入触发重复重建

---

## 17. 预估工时

按 v2 方案，实际工时应高于旧版粗估。

建议预估：

- 数据结构与迁移：1 天
- 全量构建与版本切换：1 天
- 查询接口改造：0.5 天
- 增量刷新与队列：1 天
- 前端最小配套：0.5 天
- 测试与压测：1 天

总计建议：

- **约 4~5 个工作日**

如果要求更高稳健性和完整回滚验证：

- **约 5~7 个工作日**

---

## 18. v2 结论

一句话总结：

**v2 不是简单把候选结果“塞进一张表”，而是建立“可切换版本的候选快照系统”。**

它解决的是：

- 首屏慢
- 基础筛选首次慢
- 构建期空表风险
- badge/tag 过滤不可靠
- 全量与增量刷新冲突

只要按 v2 执行，工作台就会从“请求期全量算”转为“请求期查结果”，这才是接近 1s 体验的正确路线。

