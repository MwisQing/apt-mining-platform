# 研判工作台候选快照表 — 技术实施方案

> 目标：将研判工作台 `/api/alert-candidates` 首屏加载从 **94s → <500ms**
>
> 核心思路：计算从"请求时全量 Python 装饰"改为"导入后预计算 + 请求时只查表"
>
> 适用版本：APT Mining Platform v3.1.4+

---

## 一、当前问题

### 1.1 瓶颈定位

```
请求链路（当前）:
用户请求 → SQL 去重 (2s) → Python 逐行装饰 92000 条 (84s) → 缓存 → 返回

耗时分布:
  dedup_sql_fetch:      2.077s    (SQL 去重取数)
  cross_day_lateral:    0.513s    (跨天/横向聚合)
  heat_and_source_maps: 0.901s    (热度聚合)
  event_maps:           0.175s    (事件关系)
  trace_maps:           0.176s    (追踪关系)
  device_tag_map:       0.068s    (设备标签)
  make_items:           83.818s   ← 主瓶颈（逐行 badge/评分/摘要）
  decorate_total:       109.542s  ← 含重复计算
```

### 1.2 根因

`_make_items` + `_decorate_candidate_items` 在每次请求时，对 92000 条去重候选逐行执行：
- `compute_badges()`：9 种 badge 条件判断
- `_build_relation_badges()`：事件/标签/追踪/威胁类型关系 badge（被调用了 **两次**，一次算 badges，一次算 relation_summary）
- `_fake_row()`：为每行创建 FakeRow 对象（92000 次对象创建）
- `detect_candidate_matches()`：5 条候选规则匹配
- `compute_candidate_score()`：评分计算（规则分 + 热度分 + 加减分）
- `classify_candidate_priority()`：优先级分类
- `build_candidate_reason_labels()`：原因标签拼接
- `_heat_summary()`、`candidate_summary`、`relation_summary` 等字符串拼接

### 1.3 当前缓存的局限

当前已有 `_full_cache`（按基础筛选条件分桶缓存），缓存命中时切日期很快（0.06s）。但以下条件变更会触发新桶预热（再走一遍 94s）：

- `target_type`、`device_tags`、`exclude_device_tags`
- `threat_types`、`threat_levels`、`apt_tiers`
- `hide_traced`、`hide_closed`、`alert_count_max`

---

## 二、方案概述

### 2.1 核心改动

```
改动前:
  用户请求 → SQL 取全量 → Python 逐行装饰 → 缓存 → 过滤/排序/分页

改动后:
  [导入完成后] 后台线程 → SQL 取全量 → Python 装饰 → 写入快照表
  [用户请求]   SQL 查快照表 WHERE + ORDER BY + LIMIT → JSON 字段反序列化 → 返回
```

### 2.2 数据量评估

快照表行数 = 去重候选组数（按 `device_id, target, port` 去重），远小于原始告警数：

| 告警数 | 去重后候选组数（预估） | SQLite 查询耗时 |
|-------|---------------------|---------------|
| 10 万 | ~5 万 | <50ms |
| 20 万 | ~9.25 万（实测） | <100ms |
| 70 万（7天） | ~15 万 | <100ms |
| 300 万（30天） | ~30 万 | <150ms |

SQLite 对 30 万行做 `WHERE indexed_col + ORDER BY indexed_col + LIMIT 50` 只需 10-100ms。

---

## 三、数据库设计

### 3.1 新建表 `alert_candidate_snapshots`

```sql
CREATE TABLE IF NOT EXISTS alert_candidate_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- ========== 唯一键（去重维度） ==========
    device_id    TEXT NOT NULL,
    target       TEXT NOT NULL,
    port         TEXT NOT NULL DEFAULT '',

    -- ========== 原始字段（取自 alerts 去重后代表行） ==========
    source_ip    TEXT,           -- 代表行的 source_ip
    target_type  TEXT,
    threat_type  TEXT,
    threat_level TEXT,
    std_apt_org  TEXT,
    apt_org      TEXT,
    apt_org_tier TEXT,
    alert_count  INTEGER DEFAULT 0,
    vendors      TEXT,
    protocol     TEXT,
    intel_tags   TEXT,
    dns_resolved_ip TEXT,
    asset_type   TEXT,
    analysis_status TEXT DEFAULT '',
    is_focused   INTEGER DEFAULT 0,
    first_alert_time TEXT,       -- 该组最早告警时间
    last_alert_time  TEXT,       -- 该组最晚告警时间

    -- ========== 聚合字段（需从 alerts 额外聚合） ==========
    source_ips       TEXT,       -- GROUP_CONCAT(DISTINCT source_ip)，用 " | " 分隔
    source_ip_count  INTEGER DEFAULT 0,

    -- ========== 热度（预计算） ==========
    heat_target_alert_count    INTEGER DEFAULT 0,  -- 同 target 的告警总数
    heat_target_device_count   INTEGER DEFAULT 0,  -- 同 target 涉及的设备数
    heat_device_alert_count    INTEGER DEFAULT 0,  -- 同 (device_id, target, port) 的告警数
    heat_device_target_count   INTEGER DEFAULT 0,  -- 同 device_id 对应的目标数
    heat_source_ip_alert_count INTEGER DEFAULT 0,  -- 同 source_ip 的告警数

    -- ========== 评分（预计算） ==========
    candidate_score          INTEGER DEFAULT 0,
    candidate_priority       TEXT,     -- "p1" / "p2" / "p3"
    candidate_priority_label TEXT,     -- "高优先" / "中优先" / "观察"
    candidate_rule_ids       TEXT,     -- JSON 数组: ["threat_type_apt", "std_apt_org_present"]
    candidate_reasons        TEXT,     -- JSON 数组: ["威胁类型命中APT", "已映射标准APT组织"]

    -- ========== 关系状态（预计算） ==========
    badges_json      TEXT,     -- JSON 数组: [{"name":"apt_dict","label":"APT词典","color":"red"}, ...]
    device_tags_json TEXT,     -- JSON 数组: [{"id":1,"name":"重点设备","color":"#F56C6C"}, ...]
    event_json       TEXT,     -- JSON 对象或 null: {"event_id":1,"event_name":"xxx","color":"#f00","status":"active"}
    trace_json       TEXT,     -- JSON 对象或 null: {"traced_at":"...","note":"...","active":true}
    trace_status     TEXT,     -- "active" / "expired" / "none"
    ioc_note         TEXT,     -- 追踪备注文本
    event_status     TEXT,     -- "active" / "closed" / null

    -- ========== 辅助字段 ==========
    target_kind       TEXT,     -- "ip" / "domain" / "other"
    target_kind_label TEXT,     -- "IP 视角" / "域名视角" / "其他 IOC 视角"
    cross_day         INTEGER DEFAULT 0,   -- 是否跨天持续（1/0）
    lateral           INTEGER DEFAULT 0,   -- 是否横向扩散（1/0）

    -- ========== 摘要 ==========
    heat_summary_json     TEXT,  -- JSON: {"device":"设备 5 条","source_ip":"源 IP 8 条",...}
    relation_summary      TEXT,  -- " | " 拼接的关系描述
    candidate_summary     TEXT,  -- " | " 拼接的前4条原因
    candidate_focus       TEXT,  -- "域名视角 | 目标 12 条 | 3 台设备"
    device_note_summary   TEXT,  -- 标签名拼接 "重点设备 | 排查成功"

    -- ========== 排序辅助 ==========
    sort_priority_rank       INTEGER DEFAULT 0,   -- 3=高优先 2=中优先 1=观察
    sort_rule_hits           INTEGER DEFAULT 0,
    sort_target_device_count INTEGER DEFAULT 0,
    sort_target_alert_count  INTEGER DEFAULT 0,
    sort_source_ip_alert_count INTEGER DEFAULT 0,
    sort_trace_status        TEXT,
    sort_event_status        TEXT,

    -- ========== 元信息 ==========
    updated_at TEXT,

    UNIQUE(device_id, target, port)
);
```

### 3.2 索引

```sql
-- 日期范围筛选（最重要）
CREATE INDEX IF NOT EXISTS idx_snap_first_time
    ON alert_candidate_snapshots(first_alert_time);
CREATE INDEX IF NOT EXISTS idx_snap_last_time
    ON alert_candidate_snapshots(last_alert_time);

-- 默认排序（评分降序）
CREATE INDEX IF NOT EXISTS idx_snap_score
    ON alert_candidate_snapshots(candidate_score DESC);

-- 顶部筛选条件
CREATE INDEX IF NOT EXISTS idx_snap_target_type
    ON alert_candidate_snapshots(target_type);
CREATE INDEX IF NOT EXISTS idx_snap_threat_type
    ON alert_candidate_snapshots(threat_type);
CREATE INDEX IF NOT EXISTS idx_snap_threat_level
    ON alert_candidate_snapshots(threat_level);
CREATE INDEX IF NOT EXISTS idx_snap_apt_tier
    ON alert_candidate_snapshots(apt_org_tier);
CREATE INDEX IF NOT EXISTS idx_snap_device
    ON alert_candidate_snapshots(device_id);
CREATE INDEX IF NOT EXISTS idx_snap_trace
    ON alert_candidate_snapshots(trace_status);
CREATE INDEX IF NOT EXISTS idx_snap_priority
    ON alert_candidate_snapshots(candidate_priority);

-- 关键词搜索覆盖
CREATE INDEX IF NOT EXISTS idx_snap_target
    ON alert_candidate_snapshots(target);
```

### 3.3 建表位置

在 `backend/utils/db.py` 的 `_ensure_runtime_schema()` 函数中追加建表和建索引语句。

---

## 四、快照构建（核心逻辑）

### 4.1 新增文件

建议新增 `backend/services/snapshot_builder.py`，集中快照构建逻辑。

### 4.2 全量重建流程

```python
def rebuild_candidate_snapshots(db):
    """全量重建快照表。导入完成后在后台线程调用。"""

    # 第 1 步：SQL 去重取数（复用现有逻辑）
    # 按 (device_id, target, port) 分组，保留 alert_count 最大、时间最新的行
    rows = db.execute(text("""
        SELECT sub.* FROM (
            SELECT a.*,
                ROW_NUMBER() OVER (
                    PARTITION BY a.device_id, a.target, COALESCE(a.port, '')
                    ORDER BY a.alert_count DESC, a.last_alert_time DESC, a.id DESC
                ) AS _rn
            FROM alerts a
            WHERE 1=1
        ) sub
        WHERE sub._rn = 1
    """)).fetchall()

    # 第 2 步：预加载关系数据（复用现有函数）
    cross_day_pairs, lateral_ips = _cross_day_and_lateral(db, "1=1", {})
    trace_index = _preload_trace_index(db)
    device_map, ioc_exact_map, ioc_wildcard_map = _event_maps_for_rows(db, rows)
    trace_exact_map, trace_wildcard_map = _trace_maps_for_rows(db, rows)
    tag_map = _device_tag_map_for_rows(db, rows)
    heat_maps, source_ip_maps = _heat_and_source_maps(db, "1=1", {}, rows)

    # 第 3 步：逐行计算并写入快照表
    db.execute(text("DELETE FROM alert_candidate_snapshots"))

    batch = []
    for row in rows:
        item = _build_snapshot_row(
            row, cross_day_pairs, lateral_ips, trace_index,
            ioc_exact_map, ioc_wildcard_map,
            trace_exact_map, trace_wildcard_map,
            tag_map, heat_maps, source_ip_maps,
        )
        batch.append(item)
        if len(batch) >= 1000:
            _batch_insert_snapshots(db, batch)
            batch = []

    if batch:
        _batch_insert_snapshots(db, batch)

    db.commit()
```

### 4.3 `_build_snapshot_row` 逻辑

这个函数从现有的 `_make_items` + `_decorate_candidate_items` 提取逻辑，对单行产出快照字典：

```python
def _build_snapshot_row(row, cross_day_pairs, lateral_ips, trace_index,
                         ioc_exact_map, ioc_wildcard_map,
                         trace_exact_map, trace_wildcard_map,
                         tag_map, heat_maps, source_ip_maps):
    row_dict = dict(row._mapping)
    row_dict.pop("_rn", None)

    # 1. 事件/追踪/标签匹配（现有函数）
    event_info = _event_for_row(row_dict, {}, ioc_exact_map, ioc_wildcard_map)
    trace_info = _trace_info_for_row(row_dict, trace_exact_map, trace_wildcard_map)
    device_tags = tag_map.get(row_dict.get("device_id"), [])

    # 2. Badge 计算（现有函数）
    badges = _dedupe_badges(
        compute_badges(
            _fake_row(row_dict), cross_day_pairs, lateral_ips,
            trace_info=trace_info, trace_index=trace_index,
        )
        + _build_relation_badges(row_dict, device_tags, event_info, trace_info)
    )

    # 3. 热度（从预加载的 heat_maps 取）
    sip_key = (row_dict.get("device_id") or "", row_dict.get("target") or "", row_dict.get("port") or "")
    sip_data = source_ip_maps.get(sip_key, {})
    heat = {
        "device_alert_count": heat_maps["device_alert_counts"].get(sip_key, 0),
        "device_target_count": heat_maps["device_target_counts"].get(row_dict.get("device_id"), 0),
        "source_ip_alert_count": heat_maps["source_ip_alert_counts"].get(row_dict.get("source_ip"), 0),
        "target_alert_count": heat_maps["target_alert_counts"].get(row_dict.get("target"), 0),
        "target_device_count": heat_maps["target_device_counts"].get(row_dict.get("target"), 0),
    }

    # 4. 候选规则匹配 + 评分 + 优先级（现有函数）
    matches = detect_candidate_matches(row_dict)
    score = compute_candidate_score(row_dict, matches, heat,
                                      trace_info=trace_info, event_info=event_info,
                                      device_tags=device_tags)
    priority = classify_candidate_priority(score)
    reasons = build_candidate_reason_labels(row_dict, matches, heat=heat,
                                             trace_info=trace_info, event_info=event_info,
                                             device_tags=device_tags)

    # 5. 辅助字段
    target_kind = classify_target_kind(row_dict.get("target"), row_dict.get("target_type"))
    trace_status = "active" if trace_info and trace_info.get("active") else "expired" if trace_info else "none"

    heat_summary = _heat_summary(heat)
    relation_badges = _build_relation_badges(row_dict, device_tags, event_info, trace_info)

    return {
        # 唯一键
        "device_id": row_dict.get("device_id"),
        "target": row_dict.get("target"),
        "port": row_dict.get("port") or "",
        # 原始字段
        "source_ip": row_dict.get("source_ip"),
        "target_type": row_dict.get("target_type"),
        "threat_type": row_dict.get("threat_type"),
        "threat_level": row_dict.get("threat_level"),
        "std_apt_org": row_dict.get("std_apt_org"),
        "apt_org": row_dict.get("apt_org"),
        "apt_org_tier": row_dict.get("apt_org_tier"),
        "alert_count": row_dict.get("alert_count"),
        "vendors": row_dict.get("vendors"),
        "protocol": row_dict.get("protocol"),
        "intel_tags": row_dict.get("intel_tags"),
        "dns_resolved_ip": row_dict.get("dns_resolved_ip"),
        "asset_type": row_dict.get("asset_type"),
        "analysis_status": row_dict.get("analysis_status") or "",
        "is_focused": row_dict.get("is_focused") or 0,
        "first_alert_time": str(row_dict.get("first_alert_time") or ""),
        "last_alert_time": str(row_dict.get("last_alert_time") or ""),
        # 聚合
        "source_ips": sip_data.get("source_ips", row_dict.get("source_ip") or ""),
        "source_ip_count": sip_data.get("source_ip_count", 1 if row_dict.get("source_ip") else 0),
        # 热度
        "heat_target_alert_count": heat["target_alert_count"],
        "heat_target_device_count": heat["target_device_count"],
        "heat_device_alert_count": heat["device_alert_count"],
        "heat_device_target_count": heat["device_target_count"],
        "heat_source_ip_alert_count": heat["source_ip_alert_count"],
        # 评分
        "candidate_score": score,
        "candidate_priority": priority["id"],
        "candidate_priority_label": priority["label"],
        "candidate_rule_ids": json.dumps([r["id"] for r in matches], ensure_ascii=False),
        "candidate_reasons": json.dumps(reasons, ensure_ascii=False),
        # 关系
        "badges_json": json.dumps(badges, ensure_ascii=False),
        "device_tags_json": json.dumps(device_tags, ensure_ascii=False),
        "event_json": json.dumps(event_info, ensure_ascii=False) if event_info else None,
        "trace_json": json.dumps(dict(trace_info), ensure_ascii=False) if trace_info else None,
        "trace_status": trace_status,
        "ioc_note": trace_info.get("note") if trace_info else None,
        "event_status": event_info.get("status") if event_info else None,
        # 辅助
        "target_kind": target_kind,
        "target_kind_label": _target_kind_label(target_kind),
        "cross_day": 1 if (row_dict.get("source_ip"), row_dict.get("target")) in cross_day_pairs else 0,
        "lateral": 1 if row_dict.get("source_ip") in lateral_ips else 0,
        # 摘要
        "heat_summary_json": json.dumps(heat_summary, ensure_ascii=False),
        "relation_summary": " | ".join(b["label"] for b in relation_badges),
        "candidate_summary": " | ".join(reasons[:4]),
        "candidate_focus": f"{_target_kind_label(target_kind)} | {heat_summary['target']} | {heat_summary['target_devices']}",
        "device_note_summary": " | ".join(t["name"] for t in device_tags),
        # 排序辅助
        "sort_priority_rank": priority["rank"],
        "sort_rule_hits": len(matches),
        "sort_target_device_count": heat["target_device_count"],
        "sort_target_alert_count": heat["target_alert_count"],
        "sort_source_ip_alert_count": heat["source_ip_alert_count"],
        "sort_trace_status": trace_status,
        "sort_event_status": event_info.get("status") if event_info else None,
        # 元信息
        "updated_at": datetime.now().isoformat(),
    }
```

### 4.4 批量写入

```python
def _batch_insert_snapshots(db, batch):
    """INSERT OR REPLACE 一批快照行。"""
    if not batch:
        return
    columns = list(batch[0].keys())
    placeholders = ", ".join(f":{col}" for col in columns)
    col_names = ", ".join(columns)
    db.execute(
        text(f"INSERT OR REPLACE INTO alert_candidate_snapshots ({col_names}) VALUES ({placeholders})"),
        batch,
    )
```

---

## 五、查询层改写

### 5.1 改写 `query_alert_candidates`

**位置：** `backend/api/alerts.py` 中的 `@candidate_router.get("")`

改为直接查快照表，不再走 `_query_all_candidate_items` / `_decorate_candidate_items` / `_full_cache`。

```python
@candidate_router.get("")
def query_alert_candidates(
    date_start: str = Query(None),
    date_end: str = Query(None),
    target_type: str = Query(None),
    device_tags: str = Query(None),
    exclude_device_tags: str = Query(None),
    threat_types: str = Query(None),
    threat_levels: str = Query(None),
    apt_tiers: str = Query(None),
    hide_traced: Optional[bool] = Query(None),
    hide_closed: Optional[bool] = Query(None),
    keyword: str = Query(None),
    alert_count_max: int = Query(None),
    badges_filter: str = Query(None),
    target_kind: str = Query("all"),
    sort_by: str = Query(None),
    sort_order: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100000),
    db=Depends(get_db),
):
    hide_traced, hide_closed = _resolve_hide_defaults(hide_traced, hide_closed)

    # ========== 构建 WHERE 条件（查快照表，表别名 s） ==========
    conditions = []
    params = {}

    # 日期范围
    if date_start:
        conditions.append("s.first_alert_time >= :date_start")
        params["date_start"] = f"{date_start} 00:00:00"
    if date_end:
        conditions.append("s.first_alert_time <= :date_end_bound")
        params["date_end_bound"] = f"{date_end} 23:59:59"

    # 目标类型
    if target_type:
        conditions.append("s.target_type = :target_type")
        params["target_type"] = target_type

    # 目标类别 (ip/domain/other)
    if target_kind and target_kind != "all":
        conditions.append("s.target_kind = :target_kind")
        params["target_kind"] = target_kind

    # 威胁类型（多选，LIKE 匹配）
    selected_threat_types = _csv_values(threat_types)
    if selected_threat_types:
        clauses = []
        for i, tt in enumerate(selected_threat_types):
            key = f"tt_{i}"
            clauses.append(f"COALESCE(s.threat_type, '') LIKE :{key}")
            params[key] = f"%{tt}%"
        conditions.append("(" + " OR ".join(clauses) + ")")

    # 威胁等级
    levels = _csv_values(threat_levels)
    if levels:
        placeholders = ", ".join(f":tl_{i}" for i in range(len(levels)))
        conditions.append(f"s.threat_level IN ({placeholders})")
        for i, level in enumerate(levels):
            params[f"tl_{i}"] = level

    # APT 分级
    tiers = _csv_values(apt_tiers)
    if tiers:
        placeholders = ", ".join(f":at_{i}" for i in range(len(tiers)))
        conditions.append(f"s.apt_org_tier IN ({placeholders})")
        for i, tier in enumerate(tiers):
            params[f"at_{i}"] = tier

    # 设备标签（EXISTS 子查询）
    tag_ids = _csv_values(device_tags)
    if tag_ids:
        placeholders = ", ".join(f":tag_{i}" for i in range(len(tag_ids)))
        conditions.append(
            f"EXISTS (SELECT 1 FROM device_tags dt WHERE dt.device_id = s.device_id "
            f"AND dt.tag_id IN ({placeholders}))"
        )
        for i, tid in enumerate(tag_ids):
            params[f"tag_{i}"] = tid

    # 排除设备标签
    exclude_tag_ids = _csv_values(exclude_device_tags)
    if exclude_tag_ids:
        placeholders = ", ".join(f":et_{i}" for i in range(len(exclude_tag_ids)))
        conditions.append(
            f"NOT EXISTS (SELECT 1 FROM device_tags dt WHERE dt.device_id = s.device_id "
            f"AND dt.tag_id IN ({placeholders}))"
        )
        for i, tid in enumerate(exclude_tag_ids):
            params[f"et_{i}"] = tid

    # 隐藏已追踪
    if hide_traced:
        conditions.append("s.trace_status != 'active'")

    # 隐藏已关闭事件
    if hide_closed:
        conditions.append("(s.event_status IS NULL OR s.event_status != 'closed')")

    # 告警次数上限
    if alert_count_max is not None:
        conditions.append("s.alert_count <= :alert_count_max")
        params["alert_count_max"] = alert_count_max

    # 关键词搜索
    if keyword:
        params["kw"] = f"%{keyword}%"
        conditions.append(
            "(s.device_id LIKE :kw OR s.source_ip LIKE :kw OR s.target LIKE :kw "
            "OR s.threat_type LIKE :kw OR s.apt_org LIKE :kw OR s.std_apt_org LIKE :kw)"
        )

    # Badge 筛选
    required_badges = set(_csv_values(badges_filter))
    if required_badges:
        for i, badge_name in enumerate(required_badges):
            key = f"badge_{i}"
            conditions.append(f"s.badges_json LIKE :{key}")
            params[key] = f'%"name": "{badge_name}"%'
            # 注意：如果 JSON 序列化格式不含空格，改为:
            # params[key] = f'%"name":"{badge_name}"%'

    where = " AND ".join(conditions) if conditions else "1=1"

    # ========== 排序 ==========
    SNAPSHOT_SORT_MAP = {
        "candidate_score": "s.candidate_score",
        "device_id": "s.device_id COLLATE NOCASE",
        "source_ip": "s.source_ip COLLATE NOCASE",
        "target": "s.target COLLATE NOCASE",
        "port": "s.port COLLATE NOCASE",
        "threat_type": "s.threat_type COLLATE NOCASE",
        "std_apt_org": "s.std_apt_org COLLATE NOCASE",
        "first_alert_time": "s.first_alert_time",
        "last_alert_time": "s.last_alert_time",
        "alert_count": "s.alert_count",
        "analysis_status": "s.analysis_status COLLATE NOCASE",
        "is_focused": "s.is_focused",
        "target_alert_count": "s.heat_target_alert_count",
        "target_device_count": "s.heat_target_device_count",
        "device_alert_count": "s.heat_device_alert_count",
        "device_target_count": "s.heat_device_target_count",
        "source_ip_alert_count": "s.heat_source_ip_alert_count",
        "trace_status": "CASE s.trace_status WHEN 'active' THEN 2 WHEN 'expired' THEN 1 ELSE 0 END",
    }

    sort_field, sort_direction = _normalize_candidate_sort(sort_by, sort_order)
    if not sort_field:
        sort_field = "candidate_score"
        sort_direction = "DESC"
    sort_expr = SNAPSHOT_SORT_MAP.get(sort_field, "s.candidate_score")
    order_clause = f"{sort_expr} {sort_direction}"

    # ========== 查询 ==========
    total = db.execute(
        text(f"SELECT COUNT(*) FROM alert_candidate_snapshots s WHERE {where}"),
        params,
    ).scalar() or 0

    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            f"SELECT s.* FROM alert_candidate_snapshots s "
            f"WHERE {where} ORDER BY {order_clause} "
            f"LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": offset},
    ).fetchall()

    # ========== 反序列化 JSON 字段 ==========
    items = []
    for row in rows:
        item = dict(row._mapping)
        item.pop("id", None)
        item["badges"] = json.loads(item.pop("badges_json") or "[]")
        item["device_tags"] = json.loads(item.pop("device_tags_json") or "[]")
        item["event"] = json.loads(item.pop("event_json") or "null")
        item["traced"] = json.loads(item.pop("trace_json") or "null")
        item["candidate_rule_ids"] = json.loads(item.get("candidate_rule_ids") or "[]")
        item["candidate_reasons"] = json.loads(item.get("candidate_reasons") or "[]")
        item["heat_summary"] = json.loads(item.pop("heat_summary_json") or "{}")
        item["heat"] = {
            "target_alert_count": item.pop("heat_target_alert_count", 0),
            "target_device_count": item.pop("heat_target_device_count", 0),
            "device_alert_count": item.pop("heat_device_alert_count", 0),
            "device_target_count": item.pop("heat_device_target_count", 0),
            "source_ip_alert_count": item.pop("heat_source_ip_alert_count", 0),
        }
        item["sort_signals"] = {
            "priority_rank": item.pop("sort_priority_rank", 0),
            "rule_hits": item.pop("sort_rule_hits", 0),
            "target_device_count": item.pop("sort_target_device_count", 0),
            "target_alert_count": item.pop("sort_target_alert_count", 0),
            "source_ip_alert_count": item.pop("sort_source_ip_alert_count", 0),
            "trace_status": item.pop("sort_trace_status", None),
            "event_status": item.pop("sort_event_status", None),
        }
        # 兼容字段
        item["trace_status_label"] = {
            "active": "追踪 TTL 内", "expired": "历史追踪"
        }.get(item.get("trace_status"), "未追踪")
        item["script_bucket"] = item["target_kind"] if item.get("target_kind") in {"ip", "domain"} else "other"
        items.append(item)

    # ========== filter_options（从全量快照表聚合，可缓存） ==========
    filter_options = _build_snapshot_filter_options(db, where, params)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "meta": _candidate_scope_meta(),
        "filter_options": filter_options,
    }
```

### 5.2 `filter_options` 的处理

当前 `_build_filter_options` 是从内存列表提取。改为 SQL 聚合：

```python
def _build_snapshot_filter_options(db, where, params):
    """从快照表聚合筛选选项。可考虑短期缓存。"""
    # 可以用一次查询获取多个 DISTINCT 值，或分别查询
    # 以下为简单实现，每个字段一次查询

    threat_types = [r[0] for r in db.execute(text(
        f"SELECT DISTINCT s.threat_type FROM alert_candidate_snapshots s "
        f"WHERE {where} AND COALESCE(s.threat_type, '') != '' ORDER BY s.threat_type"
    ), params).fetchall()]

    std_apt_orgs = [r[0] for r in db.execute(text(
        f"SELECT DISTINCT s.std_apt_org FROM alert_candidate_snapshots s "
        f"WHERE {where} AND COALESCE(s.std_apt_org, '') != '' ORDER BY s.std_apt_org"
    ), params).fetchall()]

    ports = [r[0] for r in db.execute(text(
        f"SELECT DISTINCT s.port FROM alert_candidate_snapshots s "
        f"WHERE {where} AND COALESCE(s.port, '') != '' ORDER BY s.port"
    ), params).fetchall()]

    # device_tags 和 badges 需要从 JSON 列解析，或者用 LIKE 近似
    # 简化方案：从全表取（不按 where 过滤），因为选项列表通常是全局的
    # 或者用 Python 对当前页结果提取（前端已有表头筛选能力）

    return {
        "threat_type": threat_types,
        "std_apt_org": std_apt_orgs,
        "port": ports,
        "priority": ["高优先", "中优先", "观察"],
        "device_tags": [],   # 前端从当前页数据提取
        "badges": [],        # 前端从当前页数据提取
        "ioc_note": None,
    }
```

---

## 六、快照刷新触发点

### 6.1 全量重建

| 触发位置 | 文件 | 调用方式 |
|---------|------|---------|
| Excel 导入完成 | `backend/api/imports.py` → `_process_excel()` 结束后 | 后台线程 `threading.Thread(target=rebuild_candidate_snapshots)` |
| 配置变更（badge 规则） | `backend/api/config.py` → `save_config()` 后 | 后台线程 |
| 手动触发 | 新增 `POST /api/snapshots/rebuild` | 同步或后台 |

**导入后触发示例：**

```python
# backend/api/imports.py  _process_excel() 结尾处
import threading
from backend.services.snapshot_builder import rebuild_candidate_snapshots

def _process_excel(file_path, source_file, import_id, db):
    # ... 现有导入逻辑 ...
    db.commit()

    # 导入完成后，后台重建快照
    def _rebuild():
        from backend.utils.db import get_session_local
        session = get_session_local()()
        try:
            rebuild_candidate_snapshots(session)
        finally:
            session.close()

    threading.Thread(target=_rebuild, daemon=True).start()
```

### 6.2 增量刷新

当标签、追踪、事件变更时，不需要全量重建。只更新受影响的行。

#### 标签变更 → 更新 `device_tags_json` + 重算评分

```python
# backend/services/snapshot_builder.py

def refresh_snapshots_for_device(db, device_id):
    """设备标签变更后，更新该设备所有快照行的标签和评分。"""
    # 重新查询该设备的标签
    tag_rows = db.execute(text("""
        SELECT t.id, t.name, t.color, t.is_permanent, t.batch_id
        FROM device_tags dt
        JOIN tags t ON t.id = dt.tag_id
        LEFT JOIN tag_batches tb ON tb.id = t.batch_id
        WHERE dt.device_id = :device_id
        AND (t.batch_id IS NULL OR tb.status IS NULL OR tb.status != 'deleted')
    """), {"device_id": device_id}).fetchall()

    device_tags = [{"id": r[0], "name": r[1], "color": r[2], "is_permanent": bool(r[3]), "batch_id": r[4]} for r in tag_rows]
    device_tags_json = json.dumps(device_tags, ensure_ascii=False)
    device_note_summary = " | ".join(t["name"] for t in device_tags)

    # 取该设备的所有快照行，重新算评分
    snap_rows = db.execute(text(
        "SELECT * FROM alert_candidate_snapshots WHERE device_id = :device_id"
    ), {"device_id": device_id}).fetchall()

    for snap_row in snap_rows:
        snap = dict(snap_row._mapping)
        # 用新标签重新计算评分
        matches = detect_candidate_matches(snap)
        trace_info_raw = snap.get("trace_json")
        trace_info = json.loads(trace_info_raw) if trace_info_raw else None
        event_info_raw = snap.get("event_json")
        event_info = json.loads(event_info_raw) if event_info_raw else None
        heat = {
            "target_alert_count": snap["heat_target_alert_count"],
            "target_device_count": snap["heat_target_device_count"],
            "device_alert_count": snap["heat_device_alert_count"],
            "device_target_count": snap["heat_device_target_count"],
            "source_ip_alert_count": snap["heat_source_ip_alert_count"],
        }
        score = compute_candidate_score(snap, matches, heat,
                                        trace_info=trace_info, event_info=event_info,
                                        device_tags=device_tags)
        priority = classify_candidate_priority(score)
        reasons = build_candidate_reason_labels(snap, matches, heat=heat,
                                                trace_info=trace_info, event_info=event_info,
                                                device_tags=device_tags)
        # 重新计算 badges
        # ... (类似 _build_snapshot_row 中的 badge 逻辑)

        db.execute(text("""
            UPDATE alert_candidate_snapshots SET
                device_tags_json = :device_tags_json,
                device_note_summary = :device_note_summary,
                candidate_score = :score,
                candidate_priority = :priority_id,
                candidate_priority_label = :priority_label,
                sort_priority_rank = :priority_rank,
                candidate_reasons = :reasons,
                candidate_summary = :summary,
                updated_at = :now
            WHERE id = :id
        """), {
            "device_tags_json": device_tags_json,
            "device_note_summary": device_note_summary,
            "score": score,
            "priority_id": priority["id"],
            "priority_label": priority["label"],
            "priority_rank": priority["rank"],
            "reasons": json.dumps(reasons, ensure_ascii=False),
            "summary": " | ".join(reasons[:4]),
            "now": datetime.now().isoformat(),
            "id": snap["id"],
        })

    db.commit()
```

#### 追踪变更 → 更新 `trace_json` / `trace_status` / `ioc_note`

```python
def refresh_snapshots_for_trace(db, target, port=None):
    """追踪变更后，更新匹配的快照行。"""
    if port:
        snap_rows = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots WHERE target = :target AND port = :port"
        ), {"target": target, "port": port}).fetchall()
    else:
        snap_rows = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots WHERE target = :target"
        ), {"target": target}).fetchall()

    # 重新查询该 target 的追踪信息
    trace_rows = db.execute(text(
        "SELECT target, COALESCE(port, '') AS port, traced_at, note FROM traced_targets WHERE target = :target"
    ), {"target": target}).fetchall()
    trace_index = _build_trace_index(trace_rows)

    for (snap_id,) in snap_rows:
        snap = dict(db.execute(text(
            "SELECT * FROM alert_candidate_snapshots WHERE id = :id"
        ), {"id": snap_id}).fetchone()._mapping)

        # 重新计算 trace 状态
        snap_port = snap.get("port") or ""
        trace_info_list = trace_index.get((target, snap_port), [])
        # ... 复用 _trace_info_for_row 逻辑计算新的 trace_status / ioc_note
        # 然后 UPDATE 对应行

    db.commit()
```

#### 事件变更 → 更新 `event_json` / `event_status`

类似模式，按受影响的 target 查快照行并更新。

### 6.3 各文件调用汇总

| 文件 | 变更点 | 调用 |
|------|-------|------|
| `backend/api/imports.py` | `_process_excel()` 完成后 | `rebuild_candidate_snapshots()`（后台线程） |
| `backend/api/tags.py` | 所有 9 个标签变更端点的 `db.commit()` 后 | `refresh_snapshots_for_device(db, device_id)`（同步，通常只影响少量行） |
| `backend/api/events.py` | 创建/更新/删除事件 + IOC 变更后 | `refresh_snapshots_for_event(db, event_id)`（同步） |
| `backend/api/traced.py` | 添加/更新/删除追踪后 | `refresh_snapshots_for_trace(db, target, port)`（同步） |
| `backend/api/config.py` | 保存配置后 | `rebuild_candidate_snapshots()`（后台线程） |

---

## 七、可清理的代码

快照表上线后，以下现有代码可以移除或标记为废弃：

| 代码 | 位置 | 说明 |
|------|------|------|
| `_full_cache` / `_candidate_cache` | alerts.py:34-41 | 进程内缓存不再需要 |
| `_full_cache_key_for_params` | alerts.py:54-70 | 缓存键函数 |
| `_evict_full_cache_if_needed` | alerts.py:87-93 | 缓存淘汰 |
| `_evict_cache_if_needed` | alerts.py:73-79 | 缓存淘汰 |
| `_invalidate_full_cache` | alerts.py:82-84 | 缓存失效（改为触发快照刷新） |
| `_query_all_candidate_items` | alerts.py:1206-1256 | 全量取数+装饰（快照构建时复用，API 不再调用） |
| `_get_sorted_candidate_view` | 原排序缓存 | 排序改为 SQL ORDER BY |
| `_filter_by_date` | alerts.py:101-113 | 日期过滤改为 SQL WHERE |
| `_filter_by_keyword` | alerts.py:116-125 | 关键词过滤改为 SQL WHERE |
| `_filter_by_target_kind` | alerts.py:128-136 | 改为 SQL WHERE |
| `_filter_by_badges` | alerts.py:139-147 | 改为 SQL WHERE LIKE |

这些代码在快照构建函数 `rebuild_candidate_snapshots` 中仍然会被间接调用（通过 `_decorate_candidate_items`），但 API 请求路径上不再需要。

---

## 八、前端兼容性

**前端不需要任何修改。**

快照表方案的返回结构与当前 `/api/alert-candidates` 完全一致：

```json
{
  "items": [ { 与现有字段完全相同 } ],
  "total": 42,
  "page": 1,
  "page_size": 100,
  "meta": { ... },
  "filter_options": { ... }
}
```

唯一的区别是 `x_cache` 字段不再返回（已无缓存概念），前端未使用此字段。

---

## 九、快照状态管理

### 9.1 快照构建状态

建议在内存中维护快照构建状态，供前端展示：

```python
_snapshot_status = {
    "status": "idle",     # idle / building / ready / error
    "last_built_at": None,
    "row_count": 0,
    "build_duration_ms": 0,
    "error": None,
}
```

可选新增接口：
- `GET /api/snapshots/status` — 返回快照构建状态
- `POST /api/snapshots/rebuild` — 手动触发重建

### 9.2 快照为空时的降级

如果快照表为空（首次部署、数据库迁移后），`query_alert_candidates` 应返回空结果并提示"快照正在构建中"，而不是 fallback 到旧的全量计算路径。

```python
# 在 query_alert_candidates 开头
snap_count = db.execute(text("SELECT COUNT(*) FROM alert_candidate_snapshots")).scalar()
if snap_count == 0:
    return {
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": page_size,
        "meta": {"snapshot_status": "building", "message": "候选快照正在构建中，请稍候..."},
    }
```

### 9.3 启动时自动构建

在 `backend/main.py` 启动时检查快照表是否为空，如果为空则触发后台重建：

```python
# backend/main.py  startup 事件
@app.on_event("startup")
def startup_event():
    # ... 现有初始化 ...
    # 检查快照表，为空则后台重建
    from backend.utils.db import get_session_local
    session = get_session_local()()
    count = session.execute(text("SELECT COUNT(*) FROM alert_candidate_snapshots")).scalar()
    session.close()
    if count == 0:
        import threading
        from backend.services.snapshot_builder import rebuild_candidate_snapshots
        def _rebuild():
            s = get_session_local()()
            try:
                rebuild_candidate_snapshots(s)
            finally:
                s.close()
        threading.Thread(target=_rebuild, daemon=True).start()
```

---

## 十、测试方案

### 10.1 正确性验证

对同一套数据，对比旧接口（全量计算）和新接口（快照查询）的返回结果：

```python
def test_snapshot_correctness():
    """验证快照表输出与原始全量计算输出一致。"""
    # 1. 调用旧的 _query_all_candidate_items 得到 old_items
    # 2. 调用 rebuild_candidate_snapshots
    # 3. 查询快照表得到 new_items
    # 4. 对比每条记录的 candidate_score, badges, trace_status, event_status 等关键字段
```

### 10.2 性能验证

```python
def test_snapshot_query_performance():
    """快照表查询应在 500ms 内返回。"""
    import time
    start = time.time()
    response = client.get("/api/alert-candidates?date_start=2026-04-29&date_end=2026-04-29&page_size=50")
    elapsed = time.time() - start
    assert elapsed < 0.5
    assert response.status_code == 200
    assert response.json()["total"] > 0
```

### 10.3 增量刷新验证

```python
def test_tag_change_updates_snapshot():
    """标签变更后快照表应同步更新。"""
    # 1. 给设备打标签
    # 2. 查快照表该设备的 device_tags_json
    # 3. 验证包含新标签
    # 4. 删除标签
    # 5. 验证快照已更新
```

---

## 十一、部署与迁移

### 11.1 迁移步骤

1. 更新代码（含 `db.py` 建表语句）
2. 启动后端 → `_ensure_runtime_schema` 自动建表
3. 首次启动时快照表为空 → startup 事件自动触发后台重建
4. 重建完成前，工作台显示"快照构建中"
5. 重建完成后，工作台正常使用

### 11.2 回滚方案

- 快照表是独立新表，不影响任何现有表
- 如果需要回滚，只需将 `query_alert_candidates` 函数恢复为旧实现
- 快照表可保留或 `DROP TABLE alert_candidate_snapshots` 清理

### 11.3 upgrade.py 兼容性

`upgrade.py` 不需要修改。新增的表由 `_ensure_runtime_schema` 自动创建，代码更新后首次启动自动生效。

---

## 十二、实施优先级

| 步骤 | 内容 | 预计工时 |
|------|------|---------|
| 1 | `db.py` 新增建表+索引 | 0.5h |
| 2 | `snapshot_builder.py` 全量重建函数 | 4h |
| 3 | `alerts.py` 改写 `query_alert_candidates` | 3h |
| 4 | `imports.py` 导入后触发重建 | 0.5h |
| 5 | `tags.py` / `events.py` / `traced.py` 增量刷新 | 3h |
| 6 | `main.py` 启动时检查+自动重建 | 0.5h |
| 7 | 正确性测试 + 性能测试 | 2h |
| 8 | 清理旧缓存代码 | 1h |
| **合计** | | **~14.5h（约 2 天）** |

---

## 附录：当前代码关键位置索引

| 功能 | 文件 | 行号 |
|------|------|------|
| 全量缓存定义 | `backend/api/alerts.py` | 34-41 |
| 缓存键生成 | `backend/api/alerts.py` | 54-70 |
| SQL 去重 (ROW_NUMBER) | `backend/api/alerts.py` | 1224-1237 |
| `_make_items` (主瓶颈) | `backend/api/alerts.py` | 590-623 |
| `_decorate_candidate_items` | `backend/api/alerts.py` | 1080-1176 |
| `_build_relation_badges` | `backend/api/alerts.py` | 510-566 |
| `_fake_row` | `backend/api/alerts.py` | 297-304 |
| `_heat_and_source_maps` | `backend/api/alerts.py` | 971-1077 |
| `_event_maps_for_rows` | `backend/api/alerts.py` | 347-389 |
| `_trace_maps_for_rows` | `backend/api/alerts.py` | 409-442 |
| `_device_tag_map_for_rows` | `backend/api/alerts.py` | 461-507 |
| `_cross_day_and_lateral` | `backend/api/alerts.py` | 260-294 |
| `_preload_trace_index` | `backend/api/alerts.py` | 339-344 |
| `query_alert_candidates` (入口) | `backend/api/alerts.py` | 1523-1619 |
| `_build_where` (筛选条件) | `backend/api/alerts.py` | 158-257 |
| `compute_badges` (9种) | `backend/services/__init__.py` | 38-110 |
| `detect_candidate_matches` | `backend/services/alert_workbench.py` | 155-160 |
| `compute_candidate_score` | `backend/services/alert_workbench.py` | 215-237 |
| `classify_candidate_priority` | `backend/services/alert_workbench.py` | 240-245 |
| `build_candidate_reason_labels` | `backend/services/alert_workbench.py` | 167-212 |
| 数据库初始化 | `backend/utils/db.py` | 40-127 |
| 导入处理 | `backend/api/imports.py` | 423-600+ |
| 标签变更端点 | `backend/api/tags.py` | 全文件 |
| 事件变更端点 | `backend/api/events.py` | 全文件 |
| 追踪变更端点 | `backend/api/traced.py` | 全文件 |
