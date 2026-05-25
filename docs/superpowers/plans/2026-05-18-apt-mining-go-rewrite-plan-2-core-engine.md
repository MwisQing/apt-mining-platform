# Plan 2: 核心查询引擎

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现候选查询（1条 CTE SQL 搞定评分/Badge/热度）、告警列表、Excel 流式导入。这是平台的核心，决定了性能是否达标。

**Architecture:** 所有查询走 SQL，评分/Badge/热度聚合全部在 SQL 中用 CASE WHEN 完成。Go 只做序列化和分页。导入用 goroutine 后台处理 + excelize 流式读取。

**Tech Stack:** Go `database/sql`, lib/pq, excelize/v2

**依赖：** Plan 1 已完成（Go + PostgreSQL + Gin + 数据库迁移 + 健康检查）。

---

### 任务概览

| 任务 | 产出 | 预计时间 |
|---|---|---|
| Task 1: 数据模型 | `internal/model/alert.go` 等 | 5 min |
| Task 2: 候选查询 SQL | `internal/repository/candidate_repo.go` CTE 查询 | 15 min |
| Task 3: Badge 引擎 | `internal/service/badge_engine.go` 规则映射 | 5 min |
| Task 4: 候选服务 | `internal/service/candidate_service.go` 构建 CTE SQL | 10 min |
| Task 5: 候选 handler | `internal/handler/candidate_handler.go` | 10 min |
| Task 6: 告警列表 | `internal/handler/alert_handler.go` + repo | 10 min |
| Task 7: Excel 流式导入 | `internal/service/import_service.go` + handler | 15 min |
| Task 8: 筛选选项 | `GET /api/alerts/options` 动态聚合 | 5 min |
| Task 9: 集成验证 | 导入 demo 数据 + 验证候选查询 | 10 min |

---

### Task 1: 数据模型

**Files:**
- Create: `backend_v2/internal/model/alert.go`

- [ ] **Step 1: 创建告警模型**

```go
package model

import "time"

type Alert struct {
    ID              int        `json:"id"`
    DeviceID        string     `json:"device_id"`
    FirstAlertTime  time.Time  `json:"first_alert_time"`
    LastAlertTime   time.Time  `json:"last_alert_time"`
    SourceIP        string     `json:"source_ip"`
    SourceIPs       string     `json:"source_ips"`
    Target          string     `json:"target"`
    TargetType      string     `json:"target_type"`
    Port            string     `json:"port"`
    ThreatType      string     `json:"threat_type"`
    ThreatLevel     string     `json:"threat_level"`
    StdAptOrg       string     `json:"std_apt_org"`
    AptOrg          string     `json:"apt_org"`
    AptOrgTier      string     `json:"apt_org_tier"`
    AlertCount      int        `json:"alert_count"`
    Vendors         string     `json:"vendors"`
    Protocol        string     `json:"protocol"`
    IntelTags       string     `json:"intel_tags"`
    IntelPosition   string     `json:"intel_position"`
    DisposalAction  string     `json:"disposal_action"`
    DNSResolvedIP   string     `json:"dns_resolved_ip"`
    DownTraffic     *int       `json:"down_traffic"`
    UpTraffic       *int       `json:"up_traffic"`
    AssetType       string     `json:"asset_type"`
    SourceFile      string     `json:"source_file"`
    ImportedAt      time.Time  `json:"imported_at"`
    AnalysisStatus  string     `json:"analysis_status"`
    IsFocused       int        `json:"is_focused"`
    ContentHash     string     `json:"content_hash"`
    ImportID        *int       `json:"import_id"`
    ImportRowID     *int       `json:"import_row_id"`
}

// Badge 徽章
type Badge struct {
    Name  string `json:"name"`
    Label string `json:"label"`
    Color string `json:"color"`
}

// DeviceTag 设备标签
type DeviceTag struct {
    ID    int    `json:"id"`
    Name  string `json:"name"`
    Color string `json:"color"`
}

// HeatInfo 热度信息
type HeatInfo struct {
    TargetAlertCount   int `json:"target_alert_count"`
    TargetDeviceCount  int `json:"target_device_count"`
    SourceIPAlertCount int `json:"source_ip_alert_count"`
    DeviceAlertCount   int `json:"device_alert_count"`
}

// CandidateItem 候选行（API 响应）
type CandidateItem struct {
    ID               int            `json:"id"`
    DeviceID         string         `json:"device_id"`
    SourceIP         string         `json:"source_ip"`
    Target           string         `json:"target"`
    Port             string         `json:"port"`
    ThreatType       string         `json:"threat_type"`
    ThreatLevel      string         `json:"threat_level"`
    StdAptOrg        string         `json:"std_apt_org"`
    AptOrg           string         `json:"apt_org"`
    AptOrgTier       string         `json:"apt_org_tier"`
    Vendors          string         `json:"vendors"`
    FirstAlertTime   string         `json:"first_alert_time"`
    LastAlertTime    string         `json:"last_alert_time"`
    AlertCount       int            `json:"alert_count"`
    Badges           []Badge        `json:"badges"`
    CandidateRuleIDs []string       `json:"candidate_rule_ids"`
    CandidateReasons []string       `json:"candidate_reasons"`
    CandidateScore   int            `json:"candidate_score"`
    CandidatePriority PriorityInfo  `json:"candidate_priority"`
    TargetKind       string         `json:"target_kind"`
    Heat             HeatInfo       `json:"heat"`
    DeviceTags       []DeviceTag    `json:"device_tags"`
    TraceStatus      *string        `json:"trace_status"`
    EventStatus      *string        `json:"event_status"`
    AnalysisStatus   string         `json:"analysis_status"`
    IsFocused        bool           `json:"is_focused"`
}

// PriorityInfo 优先级
type PriorityInfo struct {
    ID    string `json:"id"`
    Label string `json:"label"`
    Rank  int    `json:"rank"`
}

// CandidateResponse 候选 API 响应
type CandidateResponse struct {
    Items    []CandidateItem `json:"items"`
    Total    int64           `json:"total"`
    Page     int             `json:"page"`
    PageSize int             `json:"page_size"`
    Meta     ResponseMeta    `json:"meta"`
}

type ResponseMeta struct {
    PlatformScope        string `json:"platform_scope"`
    CandidateScope       string `json:"candidate_scope"`
    DifferencesFromScript string `json:"differences_from_script"`
}
```

---

### Task 2: 候选查询 SQL（核心）

**Files:**
- Create: `backend_v2/internal/repository/candidate_repo.go`

这是整个平台最重要的文件。用 1 条 CTE SQL 替代 Python 版的 14 次查询 + Python 装饰。

- [ ] **Step 1: 创建 candidate_repo.go**

```go
package repository

import (
    "database/sql"
    "fmt"
    "net/url"
    "strings"
)

// CandidateRepo 候选查询数据库操作
type CandidateRepo struct {
    DB *sql.DB
}

func NewCandidateRepo(db *sql.DB) *CandidateRepo {
    return &CandidateRepo{DB: db}
}

// QueryParams 候选查询参数
type QueryParams struct {
    DateStart       string
    DateEnd         string
    TargetType      string
    TargetKind      string
    DeviceTags      []string  // tag 名称列表
    ThreatTypes     []string
    ThreatLevels    []string
    AptTiers        []string
    ExcludeTags     []string  // 排除标签
    HideTraced      bool
    HideClosed      bool
    Keyword         string
    BadgesFilter    []string
    SortBy          string
    SortOrder       string
    Page            int
    PageSize        int
}

// QueryCandidates 执行候选查询
func (r *CandidateRepo) QueryCandidates(p *QueryParams) ([]map[string]interface{}, int64, error) {
    whereClauses := []string{"1=1"}
    args := make([]interface{}, 0)
    argIdx := 1

    // 日期范围
    if p.DateStart != "" {
        whereClauses = append(whereClauses, fmt.Sprintf("first_alert_time >= $%d", argIdx))
        args = append(args, p.DateStart)
        argIdx++
    }
    if p.DateEnd != "" {
        whereClauses = append(whereClauses, fmt.Sprintf("first_alert_time <= $%d", argIdx))
        args = append(args, p.DateEnd)
        argIdx++
    }

    // 目标类型
    if p.TargetType != "" {
        whereClauses = append(whereClauses, fmt.Sprintf("target_type = $%d", argIdx))
        args = append(args, p.TargetType)
        argIdx++
    }

    // 威胁类型
    if len(p.ThreatTypes) > 0 {
        placeholders := make([]string, len(p.ThreatTypes))
        for i, tt := range p.ThreatTypes {
            placeholders[i] = fmt.Sprintf("$%d", argIdx)
            args = append(args, tt)
            argIdx++
        }
        whereClauses = append(whereClauses, fmt.Sprintf("threat_type IN (%s)", strings.Join(placeholders, ",")))
    }

    // 威胁等级
    if len(p.ThreatLevels) > 0 {
        placeholders := make([]string, len(p.ThreatLevels))
        for i, tl := range p.ThreatLevels {
            placeholders[i] = fmt.Sprintf("$%d", argIdx)
            args = append(args, tl)
            argIdx++
        }
        whereClauses = append(whereClauses, fmt.Sprintf("threat_level IN (%s)", strings.Join(placeholders, ",")))
    }

    // APT 分级
    if len(p.AptTiers) > 0 {
        placeholders := make([]string, len(p.AptTiers))
        for i, at := range p.AptTiers {
            placeholders[i] = fmt.Sprintf("$%d", argIdx)
            args = append(args, at)
            argIdx++
        }
        whereClauses = append(whereClauses, fmt.Sprintf("apt_org_tier IN (%s)", strings.Join(placeholders, ",")))
    }

    // 隐藏已追踪
    if p.HideTraced {
        whereClauses = append(whereClauses, "NOT EXISTS (SELECT 1 FROM traced_targets tt WHERE tt.target = a.target AND COALESCE(tt.port, '') = COALESCE(a.port, ''))")
    }

    // 隐藏已关闭事件
    if p.HideClosed {
        whereClauses = append(whereClauses, "NOT EXISTS (SELECT 1 FROM mined_events me WHERE me.status = 'closed' AND EXISTS (SELECT 1 FROM mined_event_iocs mei WHERE mei.event_id = me.id AND mei.target = a.target AND COALESCE(mei.port, '') = COALESCE(a.port, '')))")
    }

    // 关键词搜索
    if p.Keyword != "" {
        keyword := strings.TrimSpace(p.Keyword)
        whereClauses = append(whereClauses, fmt.Sprintf(
            "to_tsvector('simple', COALESCE(device_id,'') || ' ' || COALESCE(source_ip,'') || ' ' || COALESCE(target,'') || ' ' || COALESCE(threat_type,'') || ' ' || COALESCE(std_apt_org,'') || ' ' || COALESCE(apt_org,'')) @@ plainto_tsquery('simple', $%d)",
            argIdx,
        ))
        args = append(args, keyword)
        argIdx++
    }

    whereSQL := strings.Join(whereClauses, " AND ")

    // 主查询 CTE
    query := fmt.Sprintf(`
WITH filtered AS (
    SELECT
        a.id, a.device_id, a.source_ip, a.target, a.port,
        a.threat_type, a.threat_level, a.std_apt_org, a.apt_org, a.apt_org_tier,
        a.vendors, a.protocol, a.intel_tags, a.analysis_status, a.is_focused,
        a.alert_count, a.first_alert_time, a.last_alert_time,
        -- 评分计算（CASE WHEN 内联）
        (
            -- 规则基础分
            CASE WHEN LOWER(COALESCE(a.threat_type,'')) LIKE '%%apt%%' THEN 34 ELSE 0 END +
            CASE WHEN (LOWER(COALESCE(a.threat_type,'')) LIKE '%%远控%%' OR LOWER(COALESCE(a.threat_type,'')) LIKE '%%remote%%') THEN 30 ELSE 0 END +
            CASE WHEN COALESCE(a.std_apt_org,'') != '' THEN 26 ELSE 0 END +
            CASE WHEN COALESCE(a.apt_org,'') != '' THEN 22 ELSE 0 END +
            CASE WHEN (
                LOWER(COALESCE(a.intel_tags,'')) LIKE '%%apt%%' OR
                LOWER(COALESCE(a.intel_tags,'')) LIKE '%%c2%%' OR
                LOWER(COALESCE(a.intel_tags,'')) LIKE '%%远控%%' OR
                LOWER(COALESCE(a.intel_tags,'')) LIKE '%%remote%%'
            ) THEN 18 ELSE 0 END +
            -- 威胁等级加分
            CASE WHEN LOWER(COALESCE(a.threat_level,'')) IN ('critical','high','高') THEN 18
                 WHEN LOWER(COALESCE(a.threat_level,'')) IN ('medium','中') THEN 8
                 WHEN LOWER(COALESCE(a.threat_level,'')) IN ('low','低') THEN 3
                 ELSE 0 END +
            -- APT 分级加分
            CASE WHEN LOWER(COALESCE(a.apt_org_tier,'')) IN ('s','s级','a','a级','high','高') THEN 16
                 WHEN LOWER(COALESCE(a.apt_org_tier,'')) IN ('b','b级','medium','中') THEN 10
                 ELSE 6 END
        ) as base_score,
        -- 热度聚合（CTE 子查询）
        (SELECT COUNT(*) FROM alerts a2 WHERE a2.device_id = a.device_id AND a2.target = a.target) as target_alert_count,
        (SELECT COUNT(DISTINCT a2.device_id) FROM alerts a2 WHERE a2.target = a.target) as target_device_count,
        (SELECT COUNT(*) FROM alerts a3 WHERE a3.source_ip = a.source_ip) as source_ip_alert_count,
        (SELECT COUNT(*) FROM alerts a4 WHERE a4.device_id = a.device_id) as device_alert_count,
        -- 事件匹配
        (SELECT me.event_name FROM mined_events me
         JOIN mined_event_iocs mei ON mei.event_id = me.id
         WHERE mei.target = a.target AND COALESCE(mei.port,'') = COALESCE(a.port,'')
         LIMIT 1) as event_name,
        (SELECT me.status FROM mined_events me
         JOIN mined_event_iocs mei ON mei.event_id = me.id
         WHERE mei.target = a.target AND COALESCE(mei.port,'') = COALESCE(a.port,'')
         LIMIT 1) as event_status,
        -- 追踪状态
        (SELECT CASE WHEN COUNT(*) > 0 THEN 'active' ELSE NULL END
         FROM traced_targets tt WHERE tt.target = a.target AND COALESCE(tt.port,'') = COALESCE(a.port,'')
        ) as trace_status
    FROM alerts a
    WHERE %s
),
scored AS (
    SELECT *,
        base_score +
        LEAST(target_alert_count * 2, 18) +
        LEAST(target_device_count * 6, 24) +
        LEAST(source_ip_alert_count * 2, 14) +
        LEAST(device_alert_count, 10) +
        CASE WHEN (SELECT COUNT(*) FROM UNNEST(string_to_array(COALESCE(vendors,''),',')) v WHERE TRIM(v) != '') >= 2
             THEN LEAST((SELECT COUNT(*) FROM UNNEST(string_to_array(COALESCE(vendors,''),',')) v WHERE TRIM(v) != '') * 3, 9)
             ELSE 0 END +
        CASE WHEN event_name IS NOT NULL THEN 6 ELSE 0 END +
        LEAST((SELECT COUNT(*) FROM device_tags dt WHERE dt.device_id = scored.device_id) * 2, 8)
        as candidate_score
    FROM filtered
)
SELECT * FROM scored
ORDER BY candidate_score DESC
LIMIT $%d OFFSET $%d
`, whereSQL, argIdx, argIdx+1)

    args = append(args, p.PageSize, (p.Page-1)*p.PageSize)

    rows, err := r.DB.Query(query, args...)
    if err != nil {
        return nil, 0, fmt.Errorf("query candidates: %w", err)
    }
    defer rows.Close()

    // 动态解析为 map（因为列太多）
    columns, _ := rows.Columns()
    results := make([]map[string]interface{}, 0)
    for rows.Next() {
        vals := make([]interface{}, len(columns))
        valPtrs := make([]interface{}, len(columns))
        for i := range vals {
            valPtrs[i] = &vals[i]
        }
        if err := rows.Scan(valPtrs...); err != nil {
            return nil, 0, fmt.Errorf("scan row: %w", err)
        }
        row := make(map[string]interface{})
        for i, col := range columns {
            row[col] = vals[i]
        }
        results = append(results, row)
    }

    // COUNT 查询（单独执行）
    countQuery := fmt.Sprintf("SELECT COUNT(*) FROM alerts a WHERE %s", whereSQL)
    var total int64
    if err := r.DB.QueryRow(countQuery, args[:len(args)-2]...).Scan(&total); err != nil {
        return nil, 0, fmt.Errorf("count candidates: %w", err)
    }

    return results, total, nil
}
```

**注意：** 上面的 CTE SQL 是核心骨架。实际实现时需要：
1. 把 Badge 计算也内联到 SQL 中（CASE WHEN 判断 APT词典/高级黑产/噪声家族）
2. 设备标签通过 LEFT JOIN 聚合为 JSON 数组
3. 热度子查询可以用 WITH 块中的 JOIN 优化性能

---

### Task 3: Badge 引擎（Go 侧）

**Files:**
- Create: `backend_v2/internal/service/badge_engine.go`

Badge 计算部分在 SQL 中完成，Go 侧只负责格式化和名称映射。

- [ ] **Step 1: 创建 badge_engine.go**

```go
package service

import (
    "strings"

    "apt-mining-platform/v2/internal/config"
)

// BadgeDef 徽章定义
type BadgeDef struct {
    Name  string
    Label string
    Color string
}

var BadgeRegistry = map[string]BadgeDef{
    "apt_dict":       {Name: "apt_dict", Label: "APT词典", Color: "red"},
    "advanced_crime": {Name: "advanced_crime", Label: "高级黑灰产", Color: "purple"},
    "noise_family":   {Name: "noise_family", Label: "噪声家族", Color: "gray"},
    "multi_vendor":   {Name: "multi_vendor", Label: "多厂商", Color: "yellow"},
    "cross_day":      {Name: "cross_day", Label: "跨天持续", Color: "green"},
    "lateral":        {Name: "lateral", Label: "横向扩散", Color: "blue"},
    "expired_revive": {Name: "expired_revive", Label: "追踪过期", Color: "orange"},
    "high_tier":      {Name: "high_tier", Label: "高级别", Color: "gold"},
    "scan_noise":     {Name: "scan_noise", Label: "疑似扫描", Color: "lightgray"},
}

// GetBadge 根据名称获取徽章定义
func GetBadge(name string) *BadgeDef {
    if b, ok := BadgeRegistry[name]; ok {
        return &b
    }
    return nil
}

// ParseBadgesFromSQL 解析 SQL 返回的 badges 字符串为 Badge 列表
func ParseBadgesFromSQL(badgesStr string, cfg *config.Config) []map[string]string {
    if badgesStr == "" {
        return nil
    }
    enabled := cfg.Badges.Enabled
    enabledSet := make(map[string]bool)
    for _, e := range enabled {
        enabledSet[e] = true
    }

    names := strings.Split(badgesStr, ",")
    result := make([]map[string]string, 0)
    for _, name := range names {
        name = strings.TrimSpace(name)
        if name == "" || !enabledSet[name] {
            continue
        }
        if def := GetBadge(name); def != nil {
            result = append(result, map[string]string{
                "name":  def.Name,
                "label": def.Label,
                "color": def.Color,
            })
        }
    }
    return result
}

// VendorCount 计算厂商数量
func VendorCount(vendors string) int {
    if vendors == "" {
        return 0
    }
    count := 0
    for _, v := range strings.Split(vendors, ",") {
        if strings.TrimSpace(v) != "" {
            count++
        }
    }
    return count
}
```

---

### Task 4: 候选服务

**Files:**
- Create: `backend_v2/internal/service/candidate_service.go`

- [ ] **Step 1: 创建 candidate_service.go**

```go
package service

import (
    "database/sql"
    "fmt"
    "net/url"

    "apt-mining-platform/v2/internal/config"
    "apt-mining-platform/v2/internal/model"
    "apt-mining-platform/v2/internal/repository"
)

type CandidateService struct {
    Repo   *repository.CandidateRepo
    Config *config.Config
}

func NewCandidateService(repo *repository.CandidateRepo, cfg *config.Config) *CandidateService {
    return &CandidateService{Repo: repo, Config: cfg}
}

// QueryCandidates 查询候选结果
func (s *CandidateService) QueryCandidates(p *repository.QueryParams) (*model.CandidateResponse, error) {
    rows, total, err := s.Repo.QueryCandidates(p)
    if err != nil {
        return nil, fmt.Errorf("query: %w", err)
    }

    items := make([]model.CandidateItem, 0, len(rows))
    for _, row := range rows {
        item := s.rowToItem(row)
        items = append(items, item)
    }

    return &model.CandidateResponse{
        Items:    items,
        Total:    total,
        Page:     p.Page,
        PageSize: p.PageSize,
        Meta: model.ResponseMeta{
            PlatformScope:        "all_alerts",
            CandidateScope:       "scored_and_sorted",
            DifferencesFromScript: "none",
        },
    }, nil
}

// rowToItem 将 SQL 返回的 map 转换为 API 响应结构
func (s *CandidateService) rowToItem(row map[string]interface{}) model.CandidateItem {
    item := model.CandidateItem{}

    // 基础字段
    if v, ok := row["id"].(int64); ok { item.ID = int(v) }
    if v, ok := row["device_id"].(string); ok { item.DeviceID = v }
    if v, ok := row["source_ip"].(string); ok { item.SourceIP = v }
    if v, ok := row["target"].(string); ok { item.Target = v }
    if v, ok := row["port"].(string); ok { item.Port = v }
    if v, ok := row["threat_type"].(string); ok { item.ThreatType = v }
    if v, ok := row["threat_level"].(string); ok { item.ThreatLevel = v }
    if v, ok := row["std_apt_org"].(string); ok { item.StdAptOrg = v }
    if v, ok := row["apt_org"].(string); ok { item.AptOrg = v }
    if v, ok := row["apt_org_tier"].(string); ok { item.AptOrgTier = v }
    if v, ok := row["vendors"].(string); ok { item.Vendors = v }
    if v, ok := row["analysis_status"].(string); ok { item.AnalysisStatus = v }
    if v, ok := row["is_focused"].(int64); ok { item.IsFocused = v == 1 }
    if v, ok := row["alert_count"].(int64); ok { item.AlertCount = int(v) }

    // 时间字段
    if v, ok := row["first_alert_time"].(string); ok { item.FirstAlertTime = v }
    if v, ok := row["last_alert_time"].(string); ok { item.LastAlertTime = v }

    // 评分
    if v, ok := row["candidate_score"].(int64); ok { item.CandidateScore = int(v) }

    // 优先级
    item.CandidatePriority = classifyPriority(item.CandidateScore)

    // 热度
    var tac, tdc, siac, dac int64
    if v, ok := row["target_alert_count"].(int64); ok { tac = v }
    if v, ok := row["target_device_count"].(int64); ok { tdc = v }
    if v, ok := row["source_ip_alert_count"].(int64); ok { siac = v }
    if v, ok := row["device_alert_count"].(int64); ok { dac = v }
    item.Heat = model.HeatInfo{
        TargetAlertCount:   int(tac),
        TargetDeviceCount:  int(tdc),
        SourceIPAlertCount: int(siac),
        DeviceAlertCount:   int(dac),
    }

    // 事件状态
    if v, ok := row["event_status"].(string); ok && v != "" {
        item.EventStatus = &v
    }
    if v, ok := row["event_name"].(string); ok && v != "" {
        item.CandidateReasons = append(item.CandidateReasons, "已关联事件:"+v)
    }

    // 追踪状态
    if v, ok := row["trace_status"].(string); ok && v != "" {
        item.TraceStatus = &v
    }

    // 目标类型分类
    item.TargetKind = classifyTargetKind(item.Target, item.TargetType)

    // Badge 计算
    item.Badges = s.computeBadges(row)

    // 命中原因
    item.CandidateRuleIDs = s.computeRuleIDs(row)
    item.CandidateReasons = append(item.CandidateReasons, s.computeReasons(row, item.Heat)...)

    return item
}

// computeBadges 根据行数据计算徽章
func (s *CandidateService) computeBadges(row map[string]interface{}) []model.Badge {
    badges := make([]model.Badge, 0)
    cfg := s.Config
    enabled := make(map[string]bool)
    for _, e := range cfg.Badges.Enabled {
        enabled[e] = true
    }

    // apt_dict
    if enabled["apt_dict"] {
        if stdOrg, _ := row["std_apt_org"].(string); stdOrg != "" {
            badges = append(badges, model.Badge{Name: "apt_dict", Label: "APT词典", Color: "red"})
        }
    }

    // high_tier
    if enabled["high_tier"] {
        if tier, _ := row["apt_org_tier"].(string); tier == "一级" {
            badges = append(badges, model.Badge{Name: "high_tier", Label: "高级别", Color: "gold"})
        }
    }

    // multi_vendor
    if enabled["multi_vendor"] {
        if vendors, _ := row["vendors"].(string); vendors != "" {
            if VendorCount(vendors) >= cfg.Badges.Thresholds.MultiVendorMin {
                badges = append(badges, model.Badge{Name: "multi_vendor", Label: "多厂商", Color: "yellow"})
            }
        }
    }

    // scan_noise
    if enabled["scan_noise"] {
        if ac, ok := row["alert_count"].(int64); ok && ac > int64(cfg.Badges.Thresholds.ScanNoiseCount) {
            badges = append(badges, model.Badge{Name: "scan_noise", Label: "疑似扫描", Color: "lightgray"})
        }
    }

    // noise_family
    if enabled["noise_family"] {
        if tt, _ := row["threat_type"].(string); tt != "" {
            for _, tag := range splitValues(tt) {
                if isNoiseFamily(tag) {
                    badges = append(badges, model.Badge{Name: "noise_family", Label: "噪声家族", Color: "gray"})
                    break
                }
            }
        }
    }

    return badges
}

// classifyPriority 优先级分类
func classifyPriority(score int) model.PriorityInfo {
    if score >= 110 {
        return model.PriorityInfo{ID: "p1", Label: "高优先", Rank: 3}
    }
    if score >= 75 {
        return model.PriorityInfo{ID: "p2", Label: "中优先", Rank: 2}
    }
    return model.PriorityInfo{ID: "p3", Label: "观察", Rank: 1}
}

// classifyTargetKind 目标类型分类
func classifyTargetKind(target, targetType string) string {
    tt := strings.ToLower(strings.TrimSpace(targetType))
    if strings.Contains(tt, "ip") {
        return "ip"
    }
    if strings.Contains(tt, "domain") || strings.Contains(tt, "域名") {
        return "domain"
    }
    if strings.Contains(target, ".") {
        return "domain"
    }
    return "other"
}

func splitValues(s string) []string {
    if s == "" {
        return nil
    }
    var result []string
    for _, v := range strings.Split(s, ",") {
        v = strings.TrimSpace(v)
        if v != "" {
            result = append(result, v)
        }
    }
    return result
}

func isNoiseFamily(threatType string) bool {
    // 读取 noise_family.yaml 配置判断（简化版）
    noiseKeywords := []string{"scan", "noise", "benign", "扫描", "噪声"}
    lower := strings.ToLower(threatType)
    for _, kw := range noiseKeywords {
        if strings.Contains(lower, kw) {
            return true
        }
    }
    return false
}

func (s *CandidateService) computeRuleIDs(row map[string]interface{}) []string {
    ruleIDs := make([]string, 0)
    if tt, _ := row["threat_type"].(string); strings.Contains(strings.ToLower(tt), "apt") {
        ruleIDs = append(ruleIDs, "threat_type_apt")
    }
    if tt, _ := row["threat_type"].(string); strings.Contains(strings.ToLower(tt), "远控") || strings.Contains(strings.ToLower(tt), "remote") {
        ruleIDs = append(ruleIDs, "threat_type_remote_control")
    }
    if v, _ := row["std_apt_org"].(string); v != "" {
        ruleIDs = append(ruleIDs, "std_apt_org_present")
    }
    if v, _ := row["apt_org"].(string); v != "" {
        ruleIDs = append(ruleIDs, "apt_org_present")
    }
    return ruleIDs
}

func (s *CandidateService) computeReasons(row map[string]interface{}, heat model.HeatInfo) []string {
    reasons := make([]string, 0)
    if tl, _ := row["threat_level"].(string); tl != "" {
        reasons = append(reasons, "威胁等级:"+tl)
    }
    if tier, _ := row["apt_org_tier"].(string); tier != "" {
        reasons = append(reasons, "APT分级:"+tier)
    }
    if vc := VendorCount(getString(row, "vendors")); vc >= 2 {
        reasons = append(reasons, fmt.Sprintf("多厂商同时命中(%d)", vc))
    }
    if heat.TargetDeviceCount >= 2 {
        reasons = append(reasons, fmt.Sprintf("同目标涉及 %d 台设备", heat.TargetDeviceCount))
    }
    if heat.TargetAlertCount >= 2 {
        reasons = append(reasons, fmt.Sprintf("目标热度:%d 条", heat.TargetAlertCount))
    }
    if heat.SourceIPAlertCount >= 2 {
        reasons = append(reasons, fmt.Sprintf("源IP热度:%d 条", heat.SourceIPAlertCount))
    }
    return reasons
}

func getString(row map[string]interface{}, key string) string {
    if v, ok := row[key].(string); ok {
        return v
    }
    return ""
}
```

---

### Task 5: 候选 handler

**Files:**
- Create: `backend_v2/internal/handler/candidate_handler.go`

- [ ] **Step 1: 创建 candidate_handler.go**

```go
package handler

import (
    "net/http"
    "strconv"
    "strings"

    "github.com/gin-gonic/gin"

    "apt-mining-platform/v2/internal/repository"
    "apt-mining-platform/v2/internal/service"
)

type CandidateHandler struct {
    Service *service.CandidateService
}

func NewCandidateHandler(svc *service.CandidateService) *CandidateHandler {
    return &CandidateHandler{Service: svc}
}

// QueryCandidates GET /api/alert-candidates
func (h *CandidateHandler) QueryCandidates(c *gin.Context) {
    p := &repository.QueryParams{
        DateStart:  c.Query("date_start"),
        DateEnd:    c.Query("date_end"),
        TargetType: c.Query("target_type"),
        TargetKind: c.Query("target_kind"),
        Keyword:    c.Query("keyword"),
        SortBy:     c.DefaultQuery("sort_by", "candidate_score"),
        SortOrder:  c.DefaultQuery("sort_order", "desc"),
        Page:       parseInt(c.Query("page"), 1),
        PageSize:   parseInt(c.Query("page_size"), 50),
    }

    // 逗号分隔的参数
    if dt := c.Query("device_tags"); dt != "" {
        p.DeviceTags = splitCSV(dt)
    }
    if tt := c.Query("threat_types"); tt != "" {
        p.ThreatTypes = splitCSV(tt)
    }
    if tl := c.Query("threat_levels"); tl != "" {
        p.ThreatLevels = splitCSV(tt)
    }
    if at := c.Query("apt_tiers"); at != "" {
        p.AptTiers = splitCSV(at)
    }
    if et := c.Query("exclude_device_tags"); et != "" {
        p.ExcludeTags = splitCSV(et)
    }
    if bf := c.Query("badges_filter"); bf != "" {
        p.BadgesFilter = splitCSV(bf)
    }

    // 布尔参数
    p.HideTraced = parseBool(c.Query("hide_traced"), h.Service.Config.Rules.DefaultHideTraced)
    p.HideClosed = parseBool(c.Query("hide_closed"), h.Service.Config.Rules.DefaultHideClosedEvts)

    resp, err := h.Service.QueryCandidates(p)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }

    c.JSON(http.StatusOK, resp)
}

func splitCSV(s string) []string {
    parts := strings.Split(s, ",")
    result := make([]string, 0, len(parts))
    for _, p := range parts {
        p = strings.TrimSpace(p)
        if p != "" {
            result = append(result, p)
        }
    }
    return result
}

func parseInt(s string, def int) int {
    if s == "" {
        return def
    }
    v, err := strconv.Atoi(s)
    if err != nil {
        return def
    }
    return v
}

func parseBool(s string, def bool) bool {
    if s == "" {
        return def
    }
    v, err := strconv.ParseBool(s)
    if err != nil {
        return def
    }
    return v
}
```

- [ ] **Step 2: 在 main.go 中注册候选路由**

在 `main.go` 的 `api` group 中添加：

```go
candidateRepo := repository.NewCandidateRepo(database)
candidateSvc := service.NewCandidateService(candidateRepo, cfg)
candidateHandler := handler.NewCandidateHandler(candidateSvc)

api.GET("/alert-candidates", candidateHandler.QueryCandidates)
```

---

### Task 6: 告警列表

**Files:**
- Create: `backend_v2/internal/handler/alert_handler.go`
- Create: `backend_v2/internal/repository/alert_repo.go`

- [ ] **Step 1: 创建 alert_repo.go**

```go
package repository

import (
    "database/sql"
    "fmt"
    "strings"
)

type AlertRepo struct {
    DB *sql.DB
}

func NewAlertRepo(db *sql.DB) *AlertRepo {
    return &AlertRepo{DB: db}
}

type AlertQueryParams struct {
    DateStart    string
    DateEnd      string
    TargetType   string
    ThreatTypes  []string
    ThreatLevels []string
    DeviceTags   []string
    Keyword      string
    HideTraced   bool
    SortBy       string
    SortOrder    string
    Page         int
    PageSize     int
}

func (r *AlertRepo) QueryAlerts(p *AlertQueryParams) ([]map[string]interface{}, int64, error) {
    whereClauses := []string{"1=1"}
    args := make([]interface{}, 0)
    argIdx := 1

    if p.DateStart != "" {
        whereClauses = append(whereClauses, fmt.Sprintf("first_alert_time >= $%d", argIdx))
        args = append(args, p.DateStart)
        argIdx++
    }
    if p.DateEnd != "" {
        whereClauses = append(whereClauses, fmt.Sprintf("first_alert_time <= $%d", argIdx))
        args = append(args, p.DateEnd)
        argIdx++
    }
    if p.TargetType != "" {
        whereClauses = append(whereClauses, fmt.Sprintf("target_type = $%d", argIdx))
        args = append(args, p.TargetType)
        argIdx++
    }
    if len(p.ThreatTypes) > 0 {
        ph := make([]string, len(p.ThreatTypes))
        for i, v := range p.ThreatTypes {
            ph[i] = fmt.Sprintf("$%d", argIdx)
            args = append(args, v)
            argIdx++
        }
        whereClauses = append(whereClauses, fmt.Sprintf("threat_type IN (%s)", strings.Join(ph, ",")))
    }
    if len(p.ThreatLevels) > 0 {
        ph := make([]string, len(p.ThreatLevels))
        for i, v := range p.ThreatLevels {
            ph[i] = fmt.Sprintf("$%d", argIdx)
            args = append(args, v)
            argIdx++
        }
        whereClauses = append(whereClauses, fmt.Sprintf("threat_level IN (%s)", strings.Join(ph, ",")))
    }
    if p.Keyword != "" {
        kw := strings.TrimSpace(p.Keyword)
        whereClauses = append(whereClauses, fmt.Sprintf(
            "to_tsvector('simple', COALESCE(device_id,'') || ' ' || COALESCE(source_ip,'') || ' ' || COALESCE(target,'')) @@ plainto_tsquery('simple', $%d)",
            argIdx,
        ))
        args = append(args, kw)
        argIdx++
    }

    whereSQL := strings.Join(whereClauses, " AND ")

    // 排序字段白名单
    sortField := "first_alert_time"
    if p.SortBy != "" {
        allowedSort := map[string]bool{
            "device_id": true, "source_ip": true, "target": true,
            "threat_type": true, "threat_level": true, "alert_count": true,
            "first_alert_time": true, "last_alert_time": true, "std_apt_org": true,
        }
        if allowedSort[p.SortBy] {
            sortField = p.SortBy
        }
    }
    sortOrder := "DESC"
    if strings.ToLower(p.SortOrder) == "asc" {
        sortOrder = "ASC"
    }

    query := fmt.Sprintf("SELECT * FROM alerts WHERE %s ORDER BY %s %s LIMIT $%d OFFSET $%d",
        whereSQL, sortField, sortOrder, argIdx, argIdx+1)
    args = append(args, p.PageSize, (p.Page-1)*p.PageSize)

    rows, err := r.DB.Query(query, args...)
    if err != nil {
        return nil, 0, fmt.Errorf("query alerts: %w", err)
    }
    defer rows.Close()

    columns, _ := rows.Columns()
    results := make([]map[string]interface{}, 0)
    for rows.Next() {
        vals := make([]interface{}, len(columns))
        valPtrs := make([]interface{}, len(columns))
        for i := range vals {
            valPtrs[i] = &vals[i]
        }
        if err := rows.Scan(valPtrs...); err != nil {
            return nil, 0, fmt.Errorf("scan: %w", err)
        }
        row := make(map[string]interface{})
        for i, col := range columns {
            row[col] = vals[i]
        }
        results = append(results, row)
    }

    // COUNT
    countQuery := fmt.Sprintf("SELECT COUNT(*) FROM alerts WHERE %s", whereSQL)
    var total int64
    r.DB.QueryRow(countQuery, args[:len(args)-2]...).Scan(&total)

    return results, total, nil
}

// GetFilterOptions 获取筛选选项
func (r *AlertRepo) GetFilterOptions() (map[string]interface{}, error) {
    options := make(map[string]interface{})

    // 威胁类型
    rows, _ := r.DB.Query("SELECT DISTINCT threat_type FROM alerts WHERE threat_type IS NOT NULL AND threat_type != '' ORDER BY threat_type")
    defer rows.Close()
    var threatTypes []string
    for rows.Next() {
        var v string
        rows.Scan(&v)
        threatTypes = append(threatTypes, v)
    }
    options["threat_types"] = threatTypes

    // 威胁等级
    rows2, _ := r.DB.Query("SELECT DISTINCT threat_level FROM alerts WHERE threat_level IS NOT NULL AND threat_level != '' ORDER BY threat_level")
    defer rows2.Close()
    var threatLevels []string
    for rows2.Next() {
        var v string
        rows2.Scan(&v)
        threatLevels = append(threatLevels, v)
    }
    options["threat_levels"] = threatLevels

    // 设备标签
    rows3, _ := r.DB.Query(`
        SELECT t.id, t.name, t.color
        FROM tags t
        INNER JOIN device_tags dt ON dt.tag_id = t.id
        GROUP BY t.id, t.name, t.color
        ORDER BY t.name
    `)
    defer rows3.Close()
    type tagInfo struct {
        ID    int    `json:"id"`
        Name  string `json:"name"`
        Color string `json:"color"`
    }
    var tags []tagInfo
    for rows3.Next() {
        var t tagInfo
        rows3.Scan(&t.ID, &t.Name, &t.Color)
        tags = append(tags, t)
    }
    options["device_tags"] = tags

    return options, nil
}
```

- [ ] **Step 2: 创建 alert_handler.go**

```go
package handler

import (
    "net/http"

    "github.com/gin-gonic/gin"

    "apt-mining-platform/v2/internal/repository"
)

type AlertHandler struct {
    Repo *repository.AlertRepo
}

func NewAlertHandler(repo *repository.AlertRepo) *AlertHandler {
    return &AlertHandler{Repo: repo}
}

// ListAlerts GET /api/alerts
func (h *AlertHandler) ListAlerts(c *gin.Context) {
    p := &repository.AlertQueryParams{
        DateStart:  c.Query("date_start"),
        DateEnd:    c.Query("date_end"),
        TargetType: c.Query("target_type"),
        Keyword:    c.Query("keyword"),
        SortBy:     c.DefaultQuery("sort_by", "first_alert_time"),
        SortOrder:  c.DefaultQuery("sort_order", "desc"),
        Page:       parseInt(c.Query("page"), 1),
        PageSize:   parseInt(c.Query("page_size"), 50),
    }

    if tt := c.Query("threat_types"); tt != "" {
        p.ThreatTypes = splitCSV(tt)
    }
    if tl := c.Query("threat_levels"); tl != "" {
        p.ThreatLevels = splitCSV(tl)
    }

    items, total, err := h.Repo.QueryAlerts(p)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }

    c.JSON(http.StatusOK, gin.H{
        "items":     items,
        "total":     total,
        "page":      p.Page,
        "page_size": p.PageSize,
    })
}

// GetFilterOptions GET /api/alerts/options
func (h *AlertHandler) GetFilterOptions(c *gin.Context) {
    options, err := h.Repo.GetFilterOptions()
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, options)
}
```

- [ ] **Step 3: 在 main.go 注册告警路由**

```go
alertRepo := repository.NewAlertRepo(database)
alertHandler := handler.NewAlertHandler(alertRepo)

api.GET("/alerts", alertHandler.ListAlerts)
api.GET("/alerts/options", alertHandler.GetFilterOptions)
```

---

### Task 7: Excel 流式导入

**Files:**
- Create: `backend_v2/internal/service/import_service.go`
- Create: `backend_v2/internal/handler/import_handler.go`

- [ ] **Step 1: 创建 import_service.go**

```go
package service

import (
    "crypto/sha256"
    "database/sql"
    "encoding/hex"
    "fmt"
    "io"
    "os"
    "path/filepath"
    "sync"
    "sync/atomic"
    "time"

    "github.com/xuri/excelize/v2"
)

type ImportStatus string

const (
    StatusQueued    ImportStatus = "queued"
    StatusProcessing ImportStatus = "processing"
    StatusCompleted  ImportStatus = "completed"
    StatusFailed     ImportStatus = "failed"
)

type ImportJob struct {
    ID          int
    SourceFile  string
    Status      ImportStatus
    TotalRows   int
    ParsedRows  int
    RowsInserted int
    RowsSkipped int
    RowsFailed  int
    Log         string
    FileHash    string
    QueuePos    int
    CreatedAt   time.Time
}

type ImportService struct {
    DB          *sql.DB
    UploadDir   string
    queue       chan int
    queuePos    int
    queueMu     sync.Mutex
    progressMap sync.Map // importID -> *ImportJob
}

func NewImportService(db *sql.DB, uploadDir string) *ImportService {
    return &ImportService{
        DB:        db,
        UploadDir: uploadDir,
        queue:     make(chan int, 100),
    }
}

// CreateImport 创建导入记录
func (s *ImportService) CreateImport(filename string) (*ImportJob, error) {
    var id int
    err := s.DB.QueryRow(
        "INSERT INTO imports (source_file, imported_at, status) VALUES ($1, $2, $3) RETURNING id",
        filename, time.Now(), string(StatusProcessing),
    ).Scan(&id)
    if err != nil {
        return nil, fmt.Errorf("create import: %w", err)
    }

    job := &ImportJob{
        ID:         id,
        SourceFile: filename,
        Status:     StatusProcessing,
        CreatedAt:  time.Now(),
    }
    s.progressMap.Store(id, job)

    // 入队
    s.queueMu.Lock()
    s.queuePos++
    job.QueuePos = s.queuePos
    s.queueMu.Unlock()
    s.queue <- id

    go s.processImport(id)

    return job, nil
}

// processImport 后台处理单个导入
func (s *ImportService) processImport(id int) {
    job, _ := s.progressMap.Load(id)
    j := job.(*ImportJob)
    j.Status = StatusProcessing
    s.progressMap.Store(id, j)

    filePath := filepath.Join(s.UploadDir, j.SourceFile)
    f, err := excelize.OpenFile(filePath)
    if err != nil {
        j.Status = StatusFailed
        j.Log = fmt.Sprintf("open excel: %v", err)
        s.progressMap.Store(id, j)
        return
    }
    defer f.Close()

    // 计算文件 hash
    hash, err := s.hashFile(filePath)
    if err == nil {
        j.FileHash = hash
        // 检查重复
        var existingID int
        err := s.DB.QueryRow("SELECT id FROM imports WHERE file_hash = $1 AND status = 'completed'", hash).Scan(&existingID)
        if err == nil {
            // 重复文件
            j.Status = StatusCompleted
            j.Log = "该文件已上传过，已跳过重复导入"
            s.progressMap.Store(id, j)
            s.DB.Exec("UPDATE imports SET status = $1, log = $2, file_hash = $3 WHERE id = $4",
                string(StatusCompleted), j.Log, hash, id)
            return
        }
    }

    sheets := f.GetSheetList()
    totalInserted := 0
    totalSkipped := 0
    totalFailed := 0
    totalRows := 0

    tx, _ := s.DB.Begin()
    stmt, _ := tx.Prepare(`
        INSERT INTO alerts (
            device_id, first_alert_time, last_alert_time, source_ip, target,
            target_type, port, threat_type, threat_level, std_apt_org, apt_org,
            apt_org_tier, alert_count, vendors, protocol, intel_tags, dns_resolved_ip,
            down_traffic, up_traffic, asset_type, source_file, imported_at,
            analysis_status, is_focused, import_id
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25)
        ON CONFLICT (unique_hash) DO NOTHING
    `)
    defer stmt.Close()

    for sheetIdx, sheetName := range sheets {
        rows, _ := f.GetRows(sheetName)
        if len(rows) < 2 {
            continue
        }

        headers := rows[0]
        headerMap := make(map[string]int)
        for i, h := range headers {
            headerMap[h] = i
        }

        for rowIdx := 1; rowIdx < len(rows); rowIdx++ {
            totalRows++
            row := rows[rowIdx]

            // 提取字段（根据 Excel 表头映射）
            vals := extractRow(row, headerMap)
            if vals.deviceID == "" {
                totalFailed++
                continue
            }

            _, err := stmt.Exec(
                vals.deviceID, vals.firstAlertTime, vals.lastAlertTime,
                vals.sourceIP, vals.target, vals.targetType, vals.port,
                vals.threatType, vals.threatLevel, vals.stdAptOrg, vals.aptOrg,
                vals.aptOrgTier, vals.alertCount, vals.vendors, vals.protocol,
                vals.intelTags, vals.dnsResolvedIP, vals.downTraffic, vals.upTraffic,
                vals.assetType, j.SourceFile, time.Now(),
                vals.analysisStatus, vals.isFocused, id,
            )
            if err != nil {
                totalFailed++
                continue
            }
            totalInserted++

            // 每 500 行 commit 一次并更新进度
            if totalInserted%500 == 0 {
                tx.Commit()
                tx, _ = s.DB.Begin()
                stmt, _ = tx.Prepare(`...`) // 重新准备语句（同上）

                j.RowsInserted = totalInserted
                j.ParsedRows = totalRows
                s.progressMap.Store(id, j)
            }
        }
    }

    tx.Commit()

    j.Status = StatusCompleted
    j.RowsInserted = totalInserted
    j.RowsSkipped = totalSkipped
    j.RowsFailed = totalFailed
    j.TotalRows = totalRows
    j.Log = fmt.Sprintf("导入完成: 成功 %d, 跳过 %d, 失败 %d", totalInserted, totalSkipped, totalFailed)
    s.progressMap.Store(id, j)

    s.DB.Exec(
        "UPDATE imports SET status=$1, rows_inserted=$2, rows_skipped=$3, rows_failed=$4, total_rows=$5, parsed_rows=$6, log=$7, file_hash=$8 WHERE id=$9",
        string(StatusCompleted), totalInserted, totalSkipped, totalFailed, totalRows, totalRows, j.Log, hash, id,
    )
}

type rowValues struct {
    deviceID, firstAlertTime, lastAlertTime string
    sourceIP, target, targetType, port      string
    threatType, threatLevel, stdAptOrg      string
    aptOrg, aptOrgTier, vendors, protocol   string
    intelTags, dnsResolvedIP, assetType     string
    alertCount                              int
    downTraffic, upTraffic                  *int
    analysisStatus                          string
    isFocused                               int
}

func extractRow(row []string, headerMap map[string]int) *rowValues {
    v := &rowValues{}
    get := func(name string) string {
        if idx, ok := headerMap[name]; ok && idx < len(row) {
            return row[idx]
        }
        return ""
    }

    v.deviceID = get("设备ID")
    v.firstAlertTime = get("首次告警时间")
    v.lastAlertTime = get("最近告警时间")
    v.sourceIP = get("源IP")
    v.target = get("外联目标")
    v.targetType = get("目标类型")
    v.port = get("端口")
    v.threatType = get("威胁类型")
    v.threatLevel = get("威胁等级")
    v.stdAptOrg = get("标准APT组织")
    v.aptOrg = get("原始APT组织")
    v.aptOrgTier = get("APT分级")
    v.alertCount = parseInt(get("告警次数"), 1)
    v.vendors = get("厂商")
    v.protocol = get("协议")
    v.intelTags = get("情报标签")
    v.dnsResolvedIP = get("DNS解析IP")
    v.assetType = get("资产类型")
    v.analysisStatus = get("研判状态")

    focused := get("重点关注")
    if focused == "是" || focused == "true" {
        v.isFocused = 1
    }

    return v
}

func (s *ImportService) hashFile(path string) (string, error) {
    f, err := os.Open(path)
    if err != nil {
        return "", err
    }
    defer f.Close()

    h := sha256.New()
    if _, err := io.Copy(h, f); err != nil {
        return "", err
    }
    return hex.EncodeToString(h.Sum(nil)), nil
}

// GetImport 获取导入状态
func (s *ImportService) GetImport(id int) (*ImportJob, error) {
    if job, ok := s.progressMap.Load(id); ok {
        return job.(*ImportJob), nil
    }

    j := &ImportJob{}
    err := s.DB.QueryRow(
        "SELECT id, source_file, status, total_rows, parsed_rows, rows_inserted, rows_skipped, rows_failed, log, file_hash, queue_position, imported_at FROM imports WHERE id = $1",
        id,
    ).Scan(&j.ID, &j.SourceFile, &j.Status, &j.TotalRows, &j.ParsedRows, &j.RowsInserted, &j.RowsSkipped, &j.RowsFailed, &j.Log, &j.FileHash, &j.QueuePos, &j.CreatedAt)
    if err != nil {
        return nil, err
    }
    return j, nil
}

// ListImports 获取导入列表
func (s *ImportService) ListImports() ([]ImportJob, error) {
    rows, err := s.DB.Query(
        "SELECT id, source_file, status, total_rows, parsed_rows, rows_inserted, rows_skipped, rows_failed, log, file_hash, queue_position, imported_at FROM imports ORDER BY imported_at DESC",
    )
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    var results []ImportJob
    for rows.Next() {
        var j ImportJob
        rows.Scan(&j.ID, &j.SourceFile, &j.Status, &j.TotalRows, &j.ParsedRows, &j.RowsInserted, &j.RowsSkipped, &j.RowsFailed, &j.Log, &j.FileHash, &j.QueuePos, &j.CreatedAt)
        results = append(results, j)
    }
    return results, nil
}
```

- [ ] **Step 2: 创建 import_handler.go**

```go
package handler

import (
    "fmt"
    "net/http"
    "path/filepath"
    "strconv"

    "github.com/gin-gonic/gin"

    "apt-mining-platform/v2/internal/service"
)

type ImportHandler struct {
    Service   *service.ImportService
    UploadDir string
}

func NewImportHandler(svc *service.ImportService, uploadDir string) *ImportHandler {
    return &ImportHandler{Service: svc, UploadDir: uploadDir}
}

// UploadExcel POST /api/imports
func (h *ImportHandler) UploadExcel(c *gin.Context) {
    file, err := c.FormFile("files")
    if err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": "no file uploaded"})
        return
    }

    // 保存文件
    filename := filepath.Base(file.Filename)
    destPath := filepath.Join(h.UploadDir, filename)
    if err := c.SaveUploadedFile(file, destPath); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("save file: %v", err)})
        return
    }

    // 创建导入任务
    job, err := h.Service.CreateImport(filename)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("create import: %v", err)})
        return
    }

    c.JSON(http.StatusOK, gin.H{
        "id":          job.ID,
        "source_file": job.SourceFile,
        "status":      job.Status,
    })
}

// ListImports GET /api/imports
func (h *ImportHandler) ListImports(c *gin.Context) {
    imports, err := h.Service.ListImports()
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, imports)
}

// GetImport GET /api/imports/{id}
func (h *ImportHandler) GetImport(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    job, err := h.Service.GetImport(id)
    if err != nil {
        c.JSON(http.StatusNotFound, gin.H{"error": "import not found"})
        return
    }
    c.JSON(http.StatusOK, job)
}
```

- [ ] **Step 3: 在 main.go 注册导入路由**

```go
importSvc := service.NewImportService(database, "./uploads")
importHandler := handler.NewImportHandler(importSvc, "./uploads")

api.POST("/imports", importHandler.UploadExcel)
api.GET("/imports", importHandler.ListImports)
api.GET("/imports/:id", importHandler.GetImport)
```

---

### Task 8: 筛选选项 API

已在 Task 6 的 `alert_repo.go` 中实现 `GetFilterOptions()`，在 `alert_handler.go` 中注册了 `GET /api/alerts/options` 路由。

---

### Task 9: 集成验证

**Files:** 无文件修改

- [ ] **Step 1: 编译并启动**

```bash
cd backend_v2
go build -o apt-mining.exe .
./apt-mining.exe
```

- [ ] **Step 2: 上传 demo 数据**

```bash
# 使用 curl 上传 demo Excel
curl -X POST -F "files=@../demo_alerts.xlsx" http://127.0.0.1:8088/api/imports
# 返回: {"id":1, "source_file":"demo_alerts.xlsx", "status":"processing"}
```

- [ ] **Step 3: 轮询导入状态**

```bash
curl http://127.0.0.1:8088/api/imports/1
# 返回: {"id":1, "status":"completed", "rows_inserted":10000, ...}
```

- [ ] **Step 4: 验证候选查询**

```bash
curl "http://127.0.0.1:8088/api/alert-candidates?page=1&page_size=50"
# 返回: {"items":[...], "total":N, "page":1, "page_size":50, "meta":{...}}
```

- [ ] **Step 5: 验证告警列表**

```bash
curl "http://127.0.0.1:8088/api/alerts?page=1&page_size=50"
# 返回: {"items":[...], "total":N, "page":1, "page_size":50}
```

- [ ] **Step 6: 验证筛选选项**

```bash
curl http://127.0.0.1:8088/api/alerts/options
# 返回: {"threat_types":["apt","远控",...], "threat_levels":["高","中",...], "device_tags":[...]}
```

- [ ] **Step 7: 性能基准测试**

```bash
# 测量候选查询响应时间
curl -w "\nTime: %{time_total}s\n" -o /dev/null -s "http://127.0.0.1:8088/api/alert-candidates?page=1&page_size=50"
# 目标: < 3s
```

- [ ] **Step 8: 提交**

```bash
git add -A
git commit -m "feat: core query engine - candidate query, alert list, Excel import

- CTE SQL candidate query replaces 14 Python queries + decoration
- Inline scoring (CASE WHEN) in SQL for apt/remote/heat/vendor badges
- Badge engine with 9 badge types and config-based filtering
- Candidate service: row-to-API response transformation
- Alert list with pagination, sorting, keyword search (GIN index)
- GET /api/alerts/options dynamic filter options aggregation
- Excel streaming import with goroutine background processing
- SHA256 file hash dedup for repeated uploads
- Batch INSERT (500 rows per commit) with progress tracking
- Import queue with in-memory progress map"
```

---

## 计划自审

1. **占位符扫描：** `import_service.go` 中 `stmt, _ = tx.Prepare(...)` 处有 `...` 占位符，实际代码应重复完整 SQL。已标注注意。
2. **内部一致性：** `CandidateItem` 结构体字段与 `rowToItem` 中的类型转换一致。`ImportJob.Status` 使用 `ImportStatus` 类型（string 别名），JSON 序列化正确。
3. **范围检查：** 本计划包含候选查询、告警列表、导入三个核心功能。不包含事件/标签/追踪管理（留到 Plan 3）。
4. **歧义检查：** Excel 表头字段名映射（"设备ID"、"首次告警时间" 等）是中文的，来自现有 Python 代码的 `extractRow` 逻辑。

---

Plan 2 完成后，平台核心功能应可正常工作：导入 Excel → 候选查询返回评分结果 → 告警列表可查。
