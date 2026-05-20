# 研判工作台预计算方案 v3 — 完整设计文档

> 日期：2026-05-14  
> 状态：待开发  
> 目标：研判工作台任何操作（选日期、筛选、排序、翻页）均 <1 秒返回

---

## 1. 问题回顾

### 1.1 现状

研判工作台 `/api/alert-candidates` 当前采用 **请求时全量计算** 架构：

- 从 `alerts` 表 SQL 查询去重后约 **92,000 行**
- 对每行在 Python 层执行：badge 计算、候选规则匹配、评分、热度查询、事件/IOC/标签关联、摘要生成
- **首次请求耗时 80-110 秒**，其中 SQL 仅占 2-6 秒，Python 装饰占 84 秒

### 1.2 历次优化尝试与局限

| 阶段 | 做了什么 | 为什么没根治 |
|------|---------|-------------|
| 阶段29 | 进程内全量缓存 `_full_cache` | 首次加载仍要 80s；换基础筛选条件缓存失效 |
| 阶段47-48 | 热度合并查询、分批 IN、缓存分桶 | SQL 阶段已不是瓶颈，Python 循环才是 |
| 阶段52 | 快照表 v2 基础设施（模型+构建器+API） | 主查询路径未切换，仍走实时计算 |
| 阶段65 | "去快照化"，改回实时查询 | 因为快照全量重建太慢，每次小改动要重跑 |

### 1.3 核心矛盾

**全量重建 vs 增量更新**：之前的快照方案只实现了全量重建（每次事件/标签/备注变更都触发 80s 重建），所以被放弃。本方案通过 **增量局部更新** 解决这个矛盾。

---

## 2. 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│ 用户操作                触发动作              耗时            │
├──────────────────────────────────────────────────────────────┤
│ 导入 Excel           → 全量构建预计算表     → 80-110s       │
│                        （导入本身就要等，可接受）              │
│                                                              │
│ 选日期/筛选/排序      → SQL 查预计算表       → <0.3s         │
│                                                              │
│ 创建/修改事件         → 增量更新受影响行     → <0.5s         │
│ 添加/编辑 IOC 备注    → 增量更新受影响行     → <0.5s         │
│ 创建/删除设备标签     → 增量更新受影响行     → <0.5s         │
│ 修改配置(badge开关等) → 全量重建             → 80-110s       │
│                        （极少操作，可接受）                    │
└──────────────────────────────────────────────────────────────┘
```

**请求路径（优化后）：**
```
前端 GET /api/alert-candidates?date_start=...&page_size=99999
  → 后端检查 snapshot_build_meta.active_version
  → 有 active version:
      → SQL 直接查 alert_candidate_snapshots 表（带 WHERE/ORDER/LIMIT）
      → badge 通过 JOIN alert_candidate_snapshot_badges 获取
      → tag 通过 JOIN alert_candidate_snapshot_tags 获取
      → 组装 JSON 返回（纯 SQL + dict 组装，无 Python 循环计算）
  → 无 active version:
      → 走旧实时路径（兜底，不应该出现）
```

---

## 3. 数据库表设计

### 3.1 复用现有表

以下三张表已存在（`backend/models/snapshot.py`），**不需要改 schema**：

- `alert_candidate_snapshots` — 主快照表，每行一条去重候选
- `alert_candidate_snapshot_badges` — badge 子表，每行一个 badge
- `alert_candidate_snapshot_tags` — tag 子表，每行一个设备标签

`snapshot_build_meta` — 构建元数据表，也已存在。

### 3.2 需要新增的索引

```sql
-- 增量更新用：按 target+port 定位受影响行（事件/IOC备注变更时）
CREATE INDEX IF NOT EXISTS idx_snap_target_port
ON alert_candidate_snapshots(snapshot_version, target, port);

-- 增量更新用：按 device_id 定位受影响行（标签变更时）
CREATE INDEX IF NOT EXISTS idx_snap_device_id
ON alert_candidate_snapshots(snapshot_version, device_id);

-- 查询用：日期范围筛选
CREATE INDEX IF NOT EXISTS idx_snap_date_range
ON alert_candidate_snapshots(snapshot_version, first_alert_time, last_alert_time);

-- 查询用：评分排序（默认排序）
CREATE INDEX IF NOT EXISTS idx_snap_score_desc
ON alert_candidate_snapshots(snapshot_version, candidate_score DESC);
```

### 3.3 新增字段（ALTER TABLE，在 `_ensure_runtime_schema` 中自动迁移）

```sql
-- 主快照表新增：存储完整 badges JSON，避免每次查询都 JOIN 子表
ALTER TABLE alert_candidate_snapshots ADD COLUMN badges_json TEXT DEFAULT '[]';

-- 主快照表新增：存储完整 device_tags JSON，避免每次查询都 JOIN 子表
ALTER TABLE alert_candidate_snapshots ADD COLUMN device_tags_json TEXT DEFAULT '[]';

-- 主快照表新增：设备关联事件 JSON（device_event 字段，独立于 IOC 事件匹配）
ALTER TABLE alert_candidate_snapshots ADD COLUMN device_event_json TEXT;
```

> **说明**：badge/tag 子表保留用于结构化筛选（如"只看有 APT词典 badge 的行"），但主查询直接读 `badges_json`/`device_tags_json` 列以避免 JOIN 开销。全量构建时同时写子表和 JSON 列。

---

## 4. 全量构建流程

### 4.1 触发时机

- Excel 导入完成后（异步，后台线程）
- 用户手动点击"重建快照"按钮（Settings 页，极少使用）
- 修改 badge 启用配置后（极少操作）

### 4.2 构建步骤（改造现有 `rebuild_candidate_snapshots`）

```python
def rebuild_candidate_snapshots(db):
    """全量构建快照。仅在导入后或配置变更后调用。"""
    version = new_snapshot_version()
    set_snapshot_building(db, version)
    
    try:
        # ① SQL 去重查询全部告警（~2s）
        rows = _fetch_all_deduped_alerts(db)  # 约 92k 行
        
        # ② 批量查询所有关系数据（~1.5s 总计）
        cross_day_pairs, lateral_ips = _cross_day_and_lateral(db, "1=1", {})
        heat_maps, source_ip_maps = _heat_and_source_maps(db, "1=1", {}, rows)
        device_events_map, ioc_exact_map, ioc_wildcard_map = _event_maps_for_rows(db, rows)
        trace_exact_map, trace_wildcard_map = _trace_maps_for_rows(db, rows)
        tag_map = _device_tag_map_for_rows(db, rows)
        trace_index = _preload_trace_index(db)
        cfg = get_config()
        
        # ③ Python 循环装饰每行（~84s，这步无法避免但只跑一次）
        snapshot_rows = []
        badge_rows = []
        tag_rows = []
        for row in rows:
            item = _decorate_single_row(
                row, cross_day_pairs, lateral_ips,
                heat_maps, source_ip_maps,
                device_events_map, ioc_exact_map, ioc_wildcard_map,
                trace_exact_map, trace_wildcard_map,
                tag_map, trace_index, cfg,
            )
            snapshot_row = _snapshot_row_from_candidate(item, version)
            snapshot_rows.append(snapshot_row)
            # ... 同时写 badge_rows, tag_rows
        
        # ④ 批量 INSERT（分批 500 行/次，~3s）
        _batch_insert_snapshots(db, snapshot_rows, badge_rows, tag_rows)
        
        # ⑤ 原子切换版本
        db.commit()
        activate_snapshot_version(db, version, len(snapshot_rows), duration_ms)
        
        # ⑥ 清理旧版本（只保留最近 2 个 version）
        _cleanup_old_versions(db, keep=2)
        
    except Exception as exc:
        db.rollback()
        set_snapshot_error(db, str(exc))
        raise
```

### 4.3 与现有构建器的关系

现有 `backend/services/snapshot_builder.py` 的 `rebuild_candidate_snapshots` 函数**已经实现了全量构建**，它调用 `alerts._query_all_candidate_items` 获取装饰好的数据再写入快照表。只需做以下调整：

1. 构建完成后写入 `badges_json` 和 `device_tags_json` 列
2. 写入 `device_event_json` 列
3. 添加旧版本清理逻辑
4. 确保构建期间旧 active_version 仍可查询（staging/active 切换模型已有）

---

## 5. 增量更新流程（核心创新点）

### 5.1 设计原则

- **只更新受影响的行**，不重建全表
- **在当前 active_version 上原地 UPDATE**，不创建新 version
- **更新粒度精确**：通过 target+port 或 device_id 定位受影响行
- **重算逻辑复用现有函数**：对受影响的少量行调用同样的装饰函数

### 5.2 事件变更后的增量更新

触发点：`POST /api/events`（创建）、`PATCH /api/events/{id}`（修改）、`DELETE /api/events/{id}`（删除）、`POST /api/events/{id}/iocs`（添加IOC）、`DELETE /api/events/{id}/iocs`（移除IOC）

```python
def patch_snapshot_for_event(db, event_id):
    """事件变更后，更新快照中受影响的行。"""
    version = get_active_snapshot_version(db)
    if not version:
        return  # 无快照，跳过
    
    # ① 获取事件关联的所有 IOC（target, port）
    iocs = db.execute(text(
        "SELECT target, COALESCE(port, '') FROM mined_event_iocs WHERE event_id = :eid"
    ), {"eid": event_id}).fetchall()
    
    # 加上事件关联的所有设备（用于 device_event 字段）
    device_ids = db.execute(text(
        "SELECT device_id FROM mined_event_devices WHERE event_id = :eid"
    ), {"eid": event_id}).fetchall()
    
    if not iocs and not device_ids:
        return
    
    # ② 找到快照中受影响的行
    #    IOC 匹配：target+port 精确匹配 或 port='' 通配
    affected_ids = set()
    for (target, port) in iocs:
        if port:
            rows = db.execute(text(
                "SELECT id FROM alert_candidate_snapshots "
                "WHERE snapshot_version = :v AND target = :t AND port IN (:p, '')"
            ), {"v": version, "t": target, "p": port}).fetchall()
        else:
            rows = db.execute(text(
                "SELECT id FROM alert_candidate_snapshots "
                "WHERE snapshot_version = :v AND target = :t"
            ), {"v": version, "t": target}).fetchall()
        affected_ids.update(r[0] for r in rows)
    
    for (device_id,) in device_ids:
        rows = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND device_id = :d"
        ), {"v": version, "d": device_id}).fetchall()
        affected_ids.update(r[0] for r in rows)
    
    if not affected_ids:
        return
    
    # ③ 重新查询当前所有事件的 IOC 映射和设备映射（全局，不只这个事件）
    all_events = _load_all_event_maps(db)  # {(target,port)->event_info, device_id->[events]}
    
    # ④ 对受影响的行逐行更新 event 相关字段
    for snap_id in affected_ids:
        snap_row = _load_snapshot_row(db, snap_id)
        new_event_info = _match_event_for_snapshot_row(snap_row, all_events)
        new_device_event = _match_device_event(snap_row, all_events)
        
        # 重算 score（需要当前行的所有信息）
        new_score = _recompute_score(snap_row, event_info=new_event_info)
        new_priority = classify_candidate_priority(new_score)
        new_reasons = _recompute_reasons(snap_row, event_info=new_event_info)
        new_badges = _recompute_badges_json(snap_row, event_info=new_event_info)
        
        db.execute(text("""
            UPDATE alert_candidate_snapshots SET
                event_json = :event_json,
                event_status = :event_status,
                device_event_json = :device_event_json,
                candidate_score = :score,
                candidate_priority = :priority,
                candidate_priority_label = :priority_label,
                candidate_reasons_json = :reasons,
                badges_json = :badges_json,
                sort_priority_rank = :priority_rank,
                sort_event_status = :event_status,
                relation_summary = :relation_summary,
                candidate_summary = :candidate_summary,
                updated_at = :updated_at
            WHERE id = :id
        """), {
            "id": snap_id,
            "event_json": json.dumps(new_event_info) if new_event_info else None,
            "event_status": new_event_info.get("status") if new_event_info else None,
            "device_event_json": json.dumps(new_device_event) if new_device_event else None,
            "score": new_score,
            "priority": new_priority["id"],
            "priority_label": new_priority["label"],
            "priority_rank": new_priority["rank"],
            "reasons": json.dumps(new_reasons, ensure_ascii=False),
            "badges_json": json.dumps(new_badges, ensure_ascii=False),
            "relation_summary": _build_relation_summary(new_badges),
            "candidate_summary": " | ".join(new_reasons[:4]),
            "updated_at": datetime.now().isoformat(),
        })
    
    # ⑤ 同步更新 badge/tag 子表（受影响行）
    _sync_badge_subtable(db, version, affected_ids)
    
    db.commit()
```

**预期耗时**：创建一个关联 3 个 IOC 的事件，影响约 100 行快照 → UPDATE 100 行 → **< 0.5 秒**。

### 5.3 IOC 备注变更后的增量更新

触发点：`POST /api/traced`（添加）、`PATCH /api/traced/{id}`（修改）、`DELETE /api/traced/{id}`（删除）、`POST /api/traced/import`（批量导入）

```python
def patch_snapshot_for_trace(db, target, port):
    """IOC 备注变更后，更新快照中受影响的行。"""
    version = get_active_snapshot_version(db)
    if not version:
        return
    
    # 定位受影响行
    if port:
        affected = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND target = :t AND port IN (:p, '')"
        ), {"v": version, "t": target, "p": port}).fetchall()
    else:
        affected = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND target = :t"
        ), {"v": version, "t": target}).fetchall()
    
    if not affected:
        return
    
    # 重新加载该 target 的追踪信息
    trace_info = _load_trace_info(db, target, port)
    
    for (snap_id,) in affected:
        snap_row = _load_snapshot_row(db, snap_id)
        new_score = _recompute_score(snap_row, trace_info=trace_info)
        new_priority = classify_candidate_priority(new_score)
        new_reasons = _recompute_reasons(snap_row, trace_info=trace_info)
        new_badges = _recompute_badges_json(snap_row, trace_info=trace_info)
        trace_status = (
            "active" if trace_info and trace_info.get("active")
            else "expired" if trace_info
            else "none"
        )
        
        db.execute(text("""
            UPDATE alert_candidate_snapshots SET
                trace_json = :trace_json,
                trace_status = :trace_status,
                ioc_note = :ioc_note,
                candidate_score = :score,
                candidate_priority = :priority,
                candidate_priority_label = :priority_label,
                candidate_reasons_json = :reasons,
                badges_json = :badges_json,
                sort_priority_rank = :priority_rank,
                sort_trace_status = :trace_status,
                relation_summary = :relation_summary,
                candidate_summary = :candidate_summary,
                updated_at = :updated_at
            WHERE id = :id
        """), { ... })
    
    _sync_badge_subtable(db, version, [r[0] for r in affected])
    db.commit()
```

**预期耗时**：添加 1 条 IOC 备注，影响约 10-50 行 → **< 0.2 秒**。

### 5.4 设备标签变更后的增量更新

触发点：`POST /api/tags/devices/tags`（打标）、`DELETE /api/tags/devices/{device_id}/tags/{tag_id}`（移除）、`POST /api/tags/batches/import-text-files`（TXT 批量打标）、`DELETE /api/tags/batches/{id}`（删除批次）、`POST /api/tags/batches/{id}/restore`（恢复批次）、`POST /api/tags/devices/batch`（批量打标）

```python
def patch_snapshot_for_device_tags(db, device_ids):
    """设备标签变更后，更新快照中受影响的行。
    
    device_ids: 受影响的设备 ID 列表（单个或批量）
    """
    version = get_active_snapshot_version(db)
    if not version:
        return
    
    for device_id in device_ids:
        affected = db.execute(text(
            "SELECT id FROM alert_candidate_snapshots "
            "WHERE snapshot_version = :v AND device_id = :d"
        ), {"v": version, "d": device_id}).fetchall()
        
        if not affected:
            continue
        
        # 重新加载该设备的标签
        new_tags = _load_device_tags(db, device_id)
        tags_json = json.dumps(new_tags, ensure_ascii=False)
        
        for (snap_id,) in affected:
            snap_row = _load_snapshot_row(db, snap_id)
            new_score = _recompute_score(snap_row, device_tags=new_tags)
            new_priority = classify_candidate_priority(new_score)
            new_reasons = _recompute_reasons(snap_row, device_tags=new_tags)
            new_badges = _recompute_badges_json(snap_row, device_tags=new_tags)
            
            db.execute(text("""
                UPDATE alert_candidate_snapshots SET
                    device_tags_json = :tags_json,
                    device_note_summary = :note_summary,
                    candidate_score = :score,
                    candidate_priority = :priority,
                    candidate_priority_label = :priority_label,
                    candidate_reasons_json = :reasons,
                    badges_json = :badges_json,
                    sort_priority_rank = :priority_rank,
                    relation_summary = :relation_summary,
                    candidate_summary = :candidate_summary,
                    updated_at = :updated_at
                WHERE id = :id
            """), { ... })
        
        _sync_tag_subtable(db, version, device_id, new_tags)
    
    db.commit()
```

**预期耗时**：TXT 批量给 500 台设备打标，每设备约 5-20 行快照 → UPDATE 约 5000 行 → **< 3 秒**。

### 5.5 增量更新中"重算 score"的实现

关键辅助函数——从快照行的已存字段 + 最新的动态数据，重算 score：

```python
def _recompute_score(snap_row, event_info=_UNSET, trace_info=_UNSET, device_tags=_UNSET):
    """从快照行的已存静态数据 + 最新动态数据，重算候选评分。
    
    _UNSET 表示"不更新这个字段，用快照行里已有的值"。
    """
    # 静态部分：从快照行读取（不需要重算，导入时已固定）
    matches = json.loads(snap_row["candidate_rule_ids_json"] or "[]")
    rule_score = _rule_ids_to_score(matches)  # 根据 rule_id 映射回对应分数
    threat_level_score = _threat_level_score(snap_row.get("threat_level"))
    tier_score = _tier_score(snap_row.get("apt_org_tier"))
    
    heat_score = (
        min(snap_row.get("heat_target_alert_count", 0) * 2, 18)
        + min(snap_row.get("heat_target_device_count", 0) * 6, 24)
        + min(snap_row.get("heat_source_ip_alert_count", 0) * 2, 14)
        + min(snap_row.get("heat_device_alert_count", 0), 10)
    )
    
    vendor_count = len(split_multi_values(snap_row.get("vendors")))
    vendor_score = min(vendor_count * 3, 9) if vendor_count >= 2 else 0
    
    base_score = rule_score + threat_level_score + tier_score + heat_score + vendor_score
    
    # 动态部分：用传入的最新数据，或回退到快照行已有值
    if trace_info is _UNSET:
        trace_info = json.loads(snap_row.get("trace_json") or "null")
    if event_info is _UNSET:
        event_info = json.loads(snap_row.get("event_json") or "null")
    if device_tags is _UNSET:
        device_tags = json.loads(snap_row.get("device_tags_json") or "[]")
    
    dynamic_score = 0
    if trace_info and trace_info.get("active"):
        dynamic_score -= 12
    elif trace_info:
        dynamic_score -= 4
    if event_info:
        dynamic_score += 6
    if device_tags:
        dynamic_score += min(len(device_tags) * 2, 8)
    
    return base_score + dynamic_score
```

> **重点**：`base_score` 完全从快照已有的静态列读取，不需要重新查 alerts 表或跑候选规则匹配。只有 trace/event/tag 的动态加减分需要实时数据。

---

## 6. 查询路径改造

### 6.1 `/api/alert-candidates` 端点改造

```python
@candidate_router.get("")
def query_alert_candidates(
    date_start, date_end, target_type, device_tags, exclude_device_tags,
    threat_types, threat_levels, apt_tiers, hide_traced, hide_closed,
    keyword, alert_count_max, badges_filter, target_kind,
    sort_by, sort_order, page, page_size,
    db=Depends(get_db),
):
    version = get_active_snapshot_version(db)
    
    if version:
        # ★ 快照路径：纯 SQL 查询，<0.3s
        return _query_from_snapshot(
            db, version,
            date_start, date_end, target_type, device_tags, exclude_device_tags,
            threat_types, threat_levels, apt_tiers, hide_traced, hide_closed,
            keyword, alert_count_max, badges_filter, target_kind,
            sort_by, sort_order, page, page_size,
        )
    else:
        # 兜底：旧实时路径（不应出现，仅在首次导入前）
        return _query_realtime(...)
```

### 6.2 快照查询实现

```python
def _query_from_snapshot(db, version, ...):
    """从预计算快照表查询，纯 SQL。"""
    
    # ① 构建 WHERE 子句
    conditions = ["s.snapshot_version = :version"]
    params = {"version": version}
    
    if date_start:
        conditions.append("s.first_alert_time >= :date_start")
        params["date_start"] = f"{date_start} 00:00:00"
    if date_end:
        conditions.append("s.first_alert_time <= :date_end")
        params["date_end"] = f"{date_end} 23:59:59"
    if target_type:
        conditions.append("s.target_type = :target_type")
        params["target_type"] = target_type
    if keyword:
        conditions.append(
            "(s.device_id LIKE :kw OR s.source_ip LIKE :kw OR s.target LIKE :kw "
            "OR s.threat_type LIKE :kw OR s.apt_org LIKE :kw OR s.std_apt_org LIKE :kw)"
        )
        params["kw"] = f"%{keyword}%"
    # ... threat_types, threat_levels, apt_tiers 同理
    
    # device_tags 筛选：通过 badge/tag 子表
    if device_tags:
        tag_ids = _csv_values(device_tags)
        placeholders = ", ".join(f":tag_{i}" for i in range(len(tag_ids)))
        conditions.append(
            f"EXISTS (SELECT 1 FROM alert_candidate_snapshot_tags st "
            f"WHERE st.snapshot_id = s.id AND st.snapshot_version = :version "
            f"AND st.tag_id IN ({placeholders}))"
        )
        for i, tid in enumerate(tag_ids):
            params[f"tag_{i}"] = tid
    
    # exclude_device_tags 排除
    if exclude_device_tags:
        etag_ids = _csv_values(exclude_device_tags)
        placeholders = ", ".join(f":et_{i}" for i in range(len(etag_ids)))
        conditions.append(
            f"NOT EXISTS (SELECT 1 FROM alert_candidate_snapshot_tags st "
            f"WHERE st.snapshot_id = s.id AND st.snapshot_version = :version "
            f"AND st.tag_id IN ({placeholders}))"
        )
        for i, tid in enumerate(etag_ids):
            params[f"et_{i}"] = tid
    
    # badges_filter 筛选
    if badges_filter:
        badge_names = _csv_values(badges_filter)
        for i, name in enumerate(badge_names):
            conditions.append(
                f"EXISTS (SELECT 1 FROM alert_candidate_snapshot_badges sb "
                f"WHERE sb.snapshot_id = s.id AND sb.snapshot_version = :version "
                f"AND sb.badge_name = :badge_{i})"
            )
            params[f"badge_{i}"] = name
    
    # target_kind 筛选
    if target_kind and target_kind != "all":
        conditions.append("s.target_kind = :target_kind")
        params["target_kind"] = target_kind
    
    # hide_traced
    if hide_traced:
        conditions.append("s.trace_status != 'active'")
    
    # hide_closed (隐藏已关闭事件关联的行)
    # 注意：原逻辑是按 IOC+端口匹配，快照表里 event_status 已预计算
    # 但这里需要注意：hide_closed 应该隐藏 event_status='closed' 的行
    # 如果事件被关闭后通过增量更新了 event_status，这里直接 WHERE 即可
    if hide_closed:
        conditions.append("COALESCE(s.event_status, '') != 'closed'")
    
    # alert_count_max
    if alert_count_max is not None:
        conditions.append("s.alert_count <= :alert_count_max")
        params["alert_count_max"] = alert_count_max
    
    where = " AND ".join(conditions)
    
    # ② 排序
    sort_map = {
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
        "trace_status": "s.sort_trace_status",
        "target_alert_count": "s.heat_target_alert_count",
        "target_device_count": "s.heat_target_device_count",
        "device_alert_count": "s.heat_device_alert_count",
        "analysis_status": "s.analysis_status COLLATE NOCASE",
        "is_focused": "s.is_focused",
    }
    sort_field, sort_direction = _normalize_candidate_sort(sort_by, sort_order)
    sort_expr = sort_map.get(sort_field, "s.candidate_score")
    order_clause = f"{sort_expr} {sort_direction}, s.first_alert_time DESC, s.id DESC"
    
    # ③ 计数
    total = db.execute(
        text(f"SELECT COUNT(*) FROM alert_candidate_snapshots s WHERE {where}"),
        params,
    ).scalar() or 0
    
    # ④ 分页查询
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = db.execute(
        text(f"""
            SELECT s.* FROM alert_candidate_snapshots s
            WHERE {where}
            ORDER BY {order_clause}
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).fetchall()
    
    # ⑤ 组装返回（纯 dict 操作，不做计算）
    items = [_snapshot_row_to_response(dict(r._mapping)) for r in rows]
    
    # ⑥ filter_options 也从快照表聚合（纯 SQL，不需要加载全量数据）
    filter_options = _build_snapshot_filter_options_v3(db, version, where, params)
    
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "meta": _candidate_scope_meta(snapshot_status="snapshot"),
        "filter_options": filter_options,
    }
```

### 6.3 `_snapshot_row_to_response`：快照行 → API 响应

```python
def _snapshot_row_to_response(snap):
    """将快照表的一行转为 API 响应格式。纯字段映射，无计算。"""
    return {
        "id": snap["id"],
        "device_id": snap["device_id"],
        "source_ip": snap["source_ip"],
        "source_ips": snap["source_ips"],
        "source_ip_count": snap["source_ip_count"],
        "target": snap["target"],
        "port": snap["port"],
        "target_type": snap["target_type"],
        "target_kind": snap["target_kind"],
        "target_kind_label": snap["target_kind_label"],
        "threat_type": snap["threat_type"],
        "threat_level": snap["threat_level"],
        "std_apt_org": snap["std_apt_org"],
        "apt_org": snap["apt_org"],
        "apt_org_tier": snap["apt_org_tier"],
        "vendors": snap["vendors"],
        "alert_count": snap["alert_count"],
        "first_alert_time": snap["first_alert_time"],
        "last_alert_time": snap["last_alert_time"],
        "analysis_status": snap["analysis_status"],
        "is_focused": bool(snap["is_focused"]),
        "badges": json.loads(snap.get("badges_json") or "[]"),
        "device_tags": json.loads(snap.get("device_tags_json") or "[]"),
        "device_event": json.loads(snap["device_event_json"]) if snap.get("device_event_json") else None,
        "event": json.loads(snap["event_json"]) if snap.get("event_json") else None,
        "event_status": snap["event_status"],
        "traced": json.loads(snap["trace_json"]) if snap.get("trace_json") else None,
        "trace_status": snap["trace_status"],
        "ioc_note": snap["ioc_note"],
        "candidate_rule_ids": json.loads(snap.get("candidate_rule_ids_json") or "[]"),
        "candidate_reasons": json.loads(snap.get("candidate_reasons_json") or "[]"),
        "candidate_score": snap["candidate_score"],
        "candidate_priority": snap["candidate_priority"],
        "candidate_priority_label": snap["candidate_priority_label"],
        "heat": {
            "target_alert_count": snap["heat_target_alert_count"],
            "target_device_count": snap["heat_target_device_count"],
            "device_alert_count": snap["heat_device_alert_count"],
            "device_target_count": snap["heat_device_target_count"],
            "source_ip_alert_count": snap["heat_source_ip_alert_count"],
        },
        "heat_summary": json.loads(snap.get("heat_summary_json") or "{}"),
        "relation_summary": snap["relation_summary"],
        "candidate_summary": snap["candidate_summary"],
        "candidate_focus": snap["candidate_focus"],
        "device_note_summary": snap["device_note_summary"],
        "sort_signals": {
            "priority_rank": snap["sort_priority_rank"],
            "rule_hits": snap["sort_rule_hits"],
            "target_device_count": snap["sort_target_device_count"],
            "target_alert_count": snap["sort_target_alert_count"],
            "source_ip_alert_count": snap["sort_source_ip_alert_count"],
            "trace_status": snap["sort_trace_status"],
            "event_status": snap["sort_event_status"],
        },
    }
```

### 6.4 filter_options 快照版本

```python
def _build_snapshot_filter_options_v3(db, version, base_where, base_params):
    """从快照表聚合筛选选项，纯 SQL。"""
    
    # 不带日期/关键词等条件的基础 WHERE（用于获取全范围的选项值）
    # 或者直接用带条件的 WHERE（只显示当前筛选范围内的选项）
    # 推荐：用带条件的 WHERE，这样筛选选项随条件联动
    
    result = {}
    
    # threat_type
    rows = db.execute(text(
        f"SELECT DISTINCT s.threat_type FROM alert_candidate_snapshots s "
        f"WHERE {base_where} AND COALESCE(s.threat_type, '') != '' ORDER BY s.threat_type"
    ), base_params).fetchall()
    result["threat_type"] = [r[0] for r in rows]
    
    # std_apt_org
    rows = db.execute(text(
        f"SELECT DISTINCT s.std_apt_org FROM alert_candidate_snapshots s "
        f"WHERE {base_where} AND COALESCE(s.std_apt_org, '') != '' ORDER BY s.std_apt_org"
    ), base_params).fetchall()
    result["std_apt_org"] = [r[0] for r in rows]
    
    # port
    rows = db.execute(text(
        f"SELECT DISTINCT s.port FROM alert_candidate_snapshots s "
        f"WHERE {base_where} AND COALESCE(s.port, '') != '' ORDER BY s.port"
    ), base_params).fetchall()
    result["port"] = [r[0] for r in rows]
    
    # priority
    result["priority"] = ["高优先", "中优先", "观察"]
    
    # device_tags: 从 tag 子表
    rows = db.execute(text(
        f"SELECT DISTINCT st.tag_name FROM alert_candidate_snapshot_tags st "
        f"JOIN alert_candidate_snapshots s ON s.id = st.snapshot_id AND s.snapshot_version = st.snapshot_version "
        f"WHERE {base_where} ORDER BY st.tag_name"
    ), base_params).fetchall()
    result["device_tags"] = [r[0] for r in rows]
    
    # badges: 从 badge 子表
    rows = db.execute(text(
        f"SELECT DISTINCT sb.badge_label FROM alert_candidate_snapshot_badges sb "
        f"JOIN alert_candidate_snapshots s ON s.id = sb.snapshot_id AND s.snapshot_version = sb.snapshot_version "
        f"WHERE {base_where} ORDER BY sb.badge_label"
    ), base_params).fetchall()
    result["badges"] = [r[0] for r in rows]
    
    result["ioc_note"] = None
    
    return result
```

---

## 7. 变更触发点清单

### 7.1 需要接入增量更新的后端接口

以下每个接口在 `db.commit()` 成功后，调用对应的 `patch_snapshot_for_*` 函数：

| 文件 | 接口 | 调用 |
|------|------|------|
| `api/events.py` | `POST /api/events` (创建事件) | `patch_snapshot_for_event(db, event_id)` |
| `api/events.py` | `PATCH /api/events/{id}` (修改事件) | `patch_snapshot_for_event(db, event_id)` |
| `api/events.py` | `DELETE /api/events/{id}` (删除事件) | `patch_snapshot_for_event(db, event_id)` ※删除前获取IOC列表 |
| `api/events.py` | `POST /api/events/{id}/iocs` (添加IOC) | `patch_snapshot_for_event(db, event_id)` |
| `api/events.py` | `DELETE /api/events/{id}/iocs` (移除IOC) | `patch_snapshot_for_event(db, event_id)` ※删除前获取IOC |
| `api/events.py` | `POST /api/events/{id}/devices` (添加设备) | `patch_snapshot_for_event(db, event_id)` |
| `api/events.py` | `DELETE /api/events/{id}/devices/{did}` (移除设备) | `patch_snapshot_for_event(db, event_id)` |
| `api/traced.py` | `POST /api/traced` (添加IOC备注) | `patch_snapshot_for_trace(db, target, port)` |
| `api/traced.py` | `PATCH /api/traced/{id}` (修改IOC备注) | `patch_snapshot_for_trace(db, target, port)` |
| `api/traced.py` | `DELETE /api/traced/{id}` (删除IOC备注) | `patch_snapshot_for_trace(db, target, port)` |
| `api/traced.py` | `POST /api/traced/import` (批量导入IOC) | 对每个唯一 target+port 调用 `patch_snapshot_for_trace` |
| `api/tags.py` | `POST /api/tags/devices/tags` (单设备打标) | `patch_snapshot_for_device_tags(db, [device_id])` |
| `api/tags.py` | `POST /api/tags/devices/batch` (批量打标) | `patch_snapshot_for_device_tags(db, device_ids)` |
| `api/tags.py` | `DELETE /api/tags/devices/{did}/tags/{tid}` (移除标签) | `patch_snapshot_for_device_tags(db, [device_id])` |
| `api/tags.py` | `POST /api/tags/batches/import-text-files` (TXT导入) | `patch_snapshot_for_device_tags(db, imported_device_ids)` |
| `api/tags.py` | `DELETE /api/tags/batches/{id}` (删除批次) | `patch_snapshot_for_device_tags(db, affected_device_ids)` |
| `api/tags.py` | `POST /api/tags/batches/{id}/restore` (恢复批次) | `patch_snapshot_for_device_tags(db, restored_device_ids)` |
| `api/tags.py` | `PATCH /api/tags/tags/{tid}` (改标签颜色) | `patch_snapshot_for_tag_color(db, tag_id)` ※特殊：只改颜色 |

### 7.2 需要触发全量重建的操作

| 文件 | 接口 | 触发 |
|------|------|------|
| `api/imports.py` | `POST /api/imports` (导入完成后) | `rebuild_candidate_snapshots_async()` |
| `api/imports.py` | `DELETE /api/imports/{id}` (删除导入) | `rebuild_candidate_snapshots_async()` |
| `api/imports.py` | `DELETE /api/imports/all` (清除全部数据) | `rebuild_candidate_snapshots_async()` |
| `api/config.py` | `POST /api/config` (badge配置变更) | `rebuild_candidate_snapshots_async()` |
| `api/snapshots.py` | `POST /api/snapshots/rebuild` (手动重建) | `rebuild_candidate_snapshots_async()` |

### 7.3 现有代码中应移除的旧缓存清理

当前 `events.py` 和 `tags.py` 中有 `_invalidate_candidate_cache()` 调用（清理 `alerts._candidate_cache`）。改造后这些应替换为 `patch_snapshot_for_*` 调用。旧的 `_candidate_cache` 和 `_full_cache` 在快照路径下不再需要，但可保留供兜底路径使用。

---

## 8. 前端改动（极小）

### 8.1 Workbench.vue

当前前端已经是 `page_size: 99999` 一次加载全量数据到前端内存，然后在前端做列筛选/排序/分页。**这个模式不需要改**。

唯一需要的改动：

```javascript
// 当前：loadData 后检查 snapshot_status
// 改造后：同样的逻辑，但后端返回速度从 80s 变为 <0.3s
// 无需前端改动

// 可选优化：如果后端返回 snapshot_status === 'building'，
// 显示"正在构建候选数据..."提示（当前已有此逻辑）
```

### 8.2 Settings.vue

导入完成后的快照构建提示逻辑当前已有（阶段63实现）。只需确保：

- 导入完成 → 轮询 `/api/snapshots/status` → 构建完成后提示刷新
- "重建快照"按钮保留在系统信息 Tab

### 8.3 事件/备注/标签操作后

当前事件/备注/标签变更后，前端会清理候选缓存并在用户返回工作台时重新 `loadData()`。改造后这个流程不变，但 `loadData()` 会在 <0.3s 内返回（因为后端已经同步完成了增量更新）。

---

## 9. 测试策略

### 9.1 全量构建测试

```python
def test_full_rebuild():
    # 导入 Excel → 验证 snapshot_build_meta 状态
    # 验证 alert_candidate_snapshots 行数 ≈ 去重后候选数
    # 验证 badges 子表行数合理
    # 验证 tags 子表行数合理
    # 验证 active_version 已切换
```

### 9.2 增量更新测试

```python
def test_patch_for_event():
    # 全量构建 → 创建事件关联 IOC (target=evil.com, port=443)
    # 验证快照中 target=evil.com,port=443 的行：
    #   event_json 非空、event_status = 'active'、score 增加了 6 分
    # 删除事件 → 验证 event_json 变 null、score 回退

def test_patch_for_trace():
    # 全量构建 → 添加 IOC 备注 (target=evil.com, port=443, note="C2服务器")
    # 验证快照中对应行：ioc_note="C2服务器"、trace_status="active"、score -12

def test_patch_for_tag():
    # 全量构建 → 给设备 LAPTOP-001 打标签"重点设备"
    # 验证快照中 device_id=LAPTOP-001 的行：device_tags_json 包含"重点设备"、score +2
```

### 9.3 查询路径测试

```python
def test_snapshot_query_basic():
    # 全量构建后 → GET /api/alert-candidates?date_start=2026-04-29&date_end=2026-04-29
    # 验证返回 items 非空、total 正确、snapshot_status="snapshot"

def test_snapshot_query_with_filters():
    # 测试各种筛选组合：keyword、badges_filter、device_tags、target_kind
    # 验证返回结果与旧实时路径一致

def test_snapshot_query_sorting():
    # 测试各种排序字段：candidate_score、first_alert_time、alert_count
    # 验证排序正确
```

### 9.4 性能测试

```python
def test_query_performance():
    # 全量构建后 → 测量 GET /api/alert-candidates 响应时间
    # 断言 < 1 秒（目标 < 0.3 秒）

def test_incremental_patch_performance():
    # 全量构建后 → 测量 patch_snapshot_for_event 耗时
    # 断言 < 1 秒
```

---

## 10. 实现文件清单

| 文件 | 改动类型 | 内容 |
|------|---------|------|
| `backend/services/snapshot_builder.py` | **重写** | 全量构建 + 3个增量更新函数 + score/badge/reason 重算辅助函数 |
| `backend/api/alerts.py` | **改造** | `query_alert_candidates` 增加快照查询路径；新增 `_query_from_snapshot`、`_snapshot_row_to_response`、`_build_snapshot_filter_options_v3` |
| `backend/api/events.py` | **修改** | 各变更接口的 commit 后调用 `patch_snapshot_for_event` |
| `backend/api/traced.py` | **修改** | 各变更接口的 commit 后调用 `patch_snapshot_for_trace` |
| `backend/api/tags.py` | **修改** | 各变更接口的 commit 后调用 `patch_snapshot_for_device_tags` |
| `backend/api/imports.py` | **修改** | 导入完成后触发 `rebuild_candidate_snapshots_async` |
| `backend/utils/db.py` | **修改** | `_ensure_runtime_schema` 添加新字段和新索引的自动迁移 |
| `backend/models/snapshot.py` | **修改** | 添加 `badges_json`、`device_tags_json`、`device_event_json` 字段 |
| `frontend/src/views/Workbench.vue` | **不改** | 无需改动（或极小调整） |
| `backend/tests/` | **新增** | 快照构建/增量更新/查询路径的回归测试 |

---

## 11. 边界情况与注意事项

### 11.1 并发安全

- 全量构建使用 `_snapshot_build_lock`（已有），同一时间只有一个构建任务
- 增量更新应在 API 请求的同步流程中执行（不用后台线程），确保 commit 前更新完成
- 增量更新期间，查询仍然可以读取快照表（SQLite WAL 模式支持读写并发）

### 11.2 构建中状态

- 全量构建期间（80-110s），旧的 active_version 仍可查询
- 新 version 在 staging 表中构建，构建完成后原子切换 `active_version`
- 前端看到 `snapshot_status: "building"` 时显示提示

### 11.3 无快照时的兜底

- 首次使用平台（未导入数据）：无快照，`active_version` 为空
- 此时走旧实时路径，返回空数据
- 首次导入完成后自动触发全量构建

### 11.4 数据一致性

- 增量更新在 API 请求的事务中同步执行，与业务数据变更在同一 commit 中
- 如果增量更新失败，整个事务回滚，业务操作也不生效
- 这保证了快照数据与业务数据始终一致

### 11.5 旧版本清理

- 每次全量构建成功后，清理除最近 2 个 version 外的所有旧数据
- 清理操作：`DELETE FROM alert_candidate_snapshots WHERE snapshot_version NOT IN (...)`
- 同步清理 badge/tag 子表

### 11.6 IOC 备注批量导入

- `POST /api/traced/import` 可能一次导入数百条备注
- 应收集所有唯一的 (target, port) 对，去重后逐个调用 `patch_snapshot_for_trace`
- 或优化为批量更新：一次性加载所有受影响的快照行，批量 UPDATE

### 11.7 事件删除前的 IOC 获取

- 删除事件时，需要先获取事件关联的 IOC 和设备列表
- 然后删除事件
- 最后用保存的 IOC/设备列表调用增量更新
- 顺序：读取 → 删除 → 更新快照
