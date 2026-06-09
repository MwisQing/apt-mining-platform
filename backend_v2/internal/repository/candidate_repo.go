package repository

import (
	"apt-mining-platform/v2/internal/config"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
)

// CandidateRepo 候选查询数据库操作
type CandidateRepo struct {
	DB *sql.DB
}

func NewCandidateRepo(db *sql.DB) *CandidateRepo {
	return &CandidateRepo{DB: db}
}

// CandidateQueryParams 候选查询参数
type CandidateQueryParams struct {
	DateStart    string
	DateEnd      string
	TargetType   string
	TargetKind   string
	DeviceTags   []string // tag 名称列表
	ThreatTypes  []string
	ThreatLevels []string
	AptTiers     []string
	AptOrgs      []string
	DeviceIDs    []string
	Ports        []string
	ExcludeTags  []string
	HideTraced   bool
	HideClosed   bool
	Keyword      string
	BadgesFilter []string
	SortBy       string
	SortOrder    string
	Page         int
	PageSize     int
}

type IocDeviceItem struct {
	DeviceID string `json:"device_id"`
	Tags     []struct {
		ID    int    `json:"id"`
		Name  string `json:"name"`
		Color string `json:"color"`
	} `json:"tags"`
}

type IocDevicesResponse struct {
	Items []IocDeviceItem `json:"items"`
}

// BuildWhereSQL 构建 WHERE 子句（返回 SQL + 参数）
func BuildWhereSQL(p *CandidateQueryParams) (string, []interface{}, int) {
	whereClauses := []string{}
	args := make([]interface{}, 0)
	argIdx := 1

	addWhere := func(cond string, vals ...interface{}) {
		whereClauses = append(whereClauses, cond)
		args = append(args, vals...)
	}

	// 日期范围
	if p.DateStart != "" {
		addWhere(fmt.Sprintf("a.first_alert_time >= $%d", argIdx), p.DateStart)
		argIdx++
	}
	if p.DateEnd != "" {
		// Use < (end_date + 1 day) to include the entire end date up to 23:59:59
		addWhere(fmt.Sprintf("a.first_alert_time < ($%d::date + interval '1 day')", argIdx), p.DateEnd)
		argIdx++
	}

	// 目标类型
	if p.TargetType != "" {
		addWhere(fmt.Sprintf("a.target_type = $%d", argIdx), p.TargetType)
		argIdx++
	}

	// 目标种类 (IP/域名/other)
	if p.TargetKind != "" && p.TargetKind != "all" {
		if p.TargetKind == "ip" {
			addWhere("(LOWER(a.target_type) LIKE '%ip%' OR a.target ~ '^[0-9]')")
		} else if p.TargetKind == "domain" {
			addWhere("(LOWER(a.target_type) LIKE '%domain%' OR LOWER(a.target_type) LIKE '%域名%' OR (a.target ~ '\\.' AND a.target !~ '^[0-9]'))")
		} else if p.TargetKind == "other" {
			addWhere("(a.target_type IS NULL OR a.target_type = '') AND a.target !~ '\\.' AND a.target !~ '^[0-9]'")
		}
	}

	// 威胁类型
	if len(p.ThreatTypes) > 0 {
		placeholders := make([]string, len(p.ThreatTypes))
		for i, tt := range p.ThreatTypes {
			placeholders[i] = fmt.Sprintf("$%d", argIdx)
			args = append(args, tt)
			argIdx++
		}
		addWhere(fmt.Sprintf("a.threat_type IN (%s)", strings.Join(placeholders, ",")))
	}

	// 威胁等级
	if len(p.ThreatLevels) > 0 {
		placeholders := make([]string, len(p.ThreatLevels))
		for i, tl := range p.ThreatLevels {
			placeholders[i] = fmt.Sprintf("$%d", argIdx)
			args = append(args, tl)
			argIdx++
		}
		addWhere(fmt.Sprintf("a.threat_level IN (%s)", strings.Join(placeholders, ",")))
	}

	// APT 分级
	if len(p.AptTiers) > 0 {
		placeholders := make([]string, len(p.AptTiers))
		for i, at := range p.AptTiers {
			placeholders[i] = fmt.Sprintf("$%d", argIdx)
			args = append(args, at)
			argIdx++
		}
		addWhere(fmt.Sprintf("a.apt_org_tier IN (%s)", strings.Join(placeholders, ",")))
	}

	// 设备标签筛选（按 tag 名称匹配）
	if len(p.DeviceTags) > 0 {
		placeholders := make([]string, len(p.DeviceTags))
		for i, tn := range p.DeviceTags {
			placeholders[i] = fmt.Sprintf("$%d", argIdx)
			args = append(args, tn)
			argIdx++
		}
		addWhere(fmt.Sprintf("EXISTS (SELECT 1 FROM device_tags dt JOIN tags t ON t.id = dt.tag_id WHERE UPPER(dt.device_id) = UPPER(a.device_id) AND t.name IN (%s))",
			strings.Join(placeholders, ",")))
	}

	// 排除标签
	if len(p.ExcludeTags) > 0 {
		placeholders := make([]string, len(p.ExcludeTags))
		for i, tn := range p.ExcludeTags {
			placeholders[i] = fmt.Sprintf("$%d", argIdx)
			args = append(args, tn)
			argIdx++
		}
		addWhere(fmt.Sprintf("NOT EXISTS (SELECT 1 FROM device_tags dt JOIN tags t ON t.id = dt.tag_id WHERE UPPER(dt.device_id) = UPPER(a.device_id) AND t.name IN (%s))",
			strings.Join(placeholders, ",")))
	}

	// 隐藏已追踪（支持 IOC 端口通配：端口为空时匹配所有端口）
	if p.HideTraced {
		addWhere("NOT EXISTS (SELECT 1 FROM traced_targets tt WHERE UPPER(tt.target) = UPPER(a.target) AND COALESCE(tt.port, '') IN ('', COALESCE(a.port, '')))")
	}

	// 隐藏已关闭事件（支持 IOC 端口通配：mei.port = '*' 匹配该目标所有端口）
	if p.HideClosed {
		addWhere("NOT EXISTS (SELECT 1 FROM mined_events me WHERE me.status = 'closed' AND EXISTS (SELECT 1 FROM mined_event_iocs mei WHERE mei.event_id = me.id AND UPPER(mei.target) = UPPER(a.target) AND (COALESCE(mei.port, '') = COALESCE(a.port, '') OR mei.port = '*')))")
	}

	// 关键词搜索（ILIKE 模糊匹配，支持中文子串）
	if p.Keyword != "" {
		keyword := "%" + strings.TrimSpace(p.Keyword) + "%"
		addWhere(fmt.Sprintf(
			"(a.device_id ILIKE $%d OR a.source_ip ILIKE $%d OR a.target ILIKE $%d OR a.threat_type ILIKE $%d OR a.std_apt_org ILIKE $%d OR a.apt_org ILIKE $%d)",
			argIdx, argIdx, argIdx, argIdx, argIdx, argIdx,
		), keyword)
		argIdx++
	}

	whereSQL := "1=1"
	if len(whereClauses) > 0 {
		whereSQL = strings.Join(whereClauses, " AND ")
	}

	// 设备ID筛选
	if len(p.DeviceIDs) > 0 {
		placeholders := make([]string, len(p.DeviceIDs))
		for i, did := range p.DeviceIDs {
			placeholders[i] = fmt.Sprintf("$%d", argIdx)
			args = append(args, did)
			argIdx++
		}
		whereSQL += fmt.Sprintf(" AND a.device_id IN (%s)", strings.Join(placeholders, ","))
	}

	// 端口筛选
	if len(p.Ports) > 0 {
		placeholders := make([]string, len(p.Ports))
		for i, pt := range p.Ports {
			placeholders[i] = fmt.Sprintf("$%d", argIdx)
			args = append(args, pt)
			argIdx++
		}
		whereSQL += fmt.Sprintf(" AND a.port IN (%s)", strings.Join(placeholders, ","))
	}

	// 标准APT组织筛选
	if len(p.AptOrgs) > 0 {
		placeholders := make([]string, len(p.AptOrgs))
		for i, ao := range p.AptOrgs {
			placeholders[i] = fmt.Sprintf("$%d", argIdx)
			args = append(args, ao)
			argIdx++
		}
		whereSQL += fmt.Sprintf(" AND a.std_apt_org IN (%s)", strings.Join(placeholders, ","))
	}

	return whereSQL, args, argIdx
}

// CandidateRow 候选行原始数据（通过 json_build_object 从 SQL 获取，避免类型断言问题）
type CandidateRow struct {
	ID                    int64           `json:"id"`
	DeviceID              string          `json:"device_id"`
	SourceIP              string          `json:"source_ip"`
	Target                string          `json:"target"`
	Port                  string          `json:"port"`
	ThreatType            string          `json:"threat_type"`
	ThreatLevel           string          `json:"threat_level"`
	StdAptOrg             string          `json:"std_apt_org"`
	AptOrg                string          `json:"apt_org"`
	AptOrgTier            string          `json:"apt_org_tier"`
	Vendors               string          `json:"vendors"`
	Protocol              string          `json:"protocol"`
	IntelTags             string          `json:"intel_tags"`
	AnalysisStatus        string          `json:"analysis_status"`
	IsFocused             int             `json:"is_focused"`
	AlertCount            int             `json:"alert_count"`
	FirstAlertTime        string          `json:"first_alert_time"`
	LastAlertTime         string          `json:"last_alert_time"`
	HeatTargetAlertCount  int             `json:"heat_target_alert_count"`
	HeatTargetDeviceCount int             `json:"heat_target_device_count"`
	HeatSourceIPAlertCnt  int             `json:"heat_source_ip_alert_count"`
	HeatDeviceAlertCount  int             `json:"heat_device_alert_count"`
	DeviceIDCount         int             `json:"device_id_count"`
	SourceIPCount         int             `json:"source_ip_count"`
	EventID               *int64          `json:"event_id"`
	EventName             *string         `json:"event_name"`
	EventStatus           *string         `json:"event_status"`
	EventColor            string          `json:"event_color"`
	EventDeviceMatch      int             `json:"event_device_match"`
	TraceStatus           *string         `json:"trace_status"`
	TraceNote             string          `json:"trace_note"`
	DeviceTagsJSON        json.RawMessage `json:"device_tags_json"`
	CandidateScore        int             `json:"candidate_score"`
}

// QueryCandidates 执行候选查询
func (r *CandidateRepo) QueryCandidates(p *CandidateQueryParams) ([]CandidateRow, int64, error) {
	traceTTL := config.Get().Rules.TraceTTLDays
	if traceTTL <= 0 {
		traceTTL = 30 // default fallback
	}

	whereSQL, args, argIdx := BuildWhereSQL(p)
	nWhereArgs := len(args) // save before appending traceTTL/pageSize/offset

	// 排序字段白名单
	sortField := "candidate_score"
	sortOrder := "DESC"
	if p.SortBy != "" {
		allowedSort := map[string]bool{
			"candidate_score": true, "device_id": true, "source_ip": true, "target": true,
			"threat_type": true, "threat_level": true, "alert_count": true,
			"first_alert_time": true, "last_alert_time": true, "std_apt_org": true,
			"apt_org_tier": true, "analysis_status": true, "is_focused": true,
			"device_id_count": true,
		}
		if allowedSort[p.SortBy] {
			sortField = p.SortBy
		}
	}
	if strings.ToLower(p.SortOrder) == "asc" {
		sortOrder = "ASC"
	}

	// 主查询：直接查询 alerts 表，不做去重，每行独立评分
	// 所有评分计算在 SQL 中完成（CASE WHEN 内联），Go 只负责反序列化
	query := fmt.Sprintf(`
WITH base AS (
    SELECT a.* FROM alerts a WHERE %s
),
heat AS (
    SELECT
        device_id, target,
        COUNT(*) AS target_alert_count,
        COUNT(DISTINCT device_id) AS target_device_count
    FROM base GROUP BY device_id, target
),
source_ip_heat AS (
    SELECT source_ip, COUNT(*) AS source_ip_alert_count FROM base GROUP BY source_ip
),
device_heat AS (
    SELECT device_id, COUNT(*) AS device_alert_count FROM base GROUP BY device_id
),
events AS (
    SELECT sub.target, sub.port, sub.event_id, sub.event_name, sub.event_status, sub.event_color
    FROM (
        SELECT mei.target, COALESCE(mei.port, '') AS port, me.id AS event_id, me.event_name, me.status AS event_status, COALESCE(me.color, '') AS event_color,
               ROW_NUMBER() OVER (PARTITION BY UPPER(mei.target), COALESCE(mei.port, '') ORDER BY me.id) AS _rn
        FROM mined_event_iocs mei
        JOIN mined_events me ON me.id = mei.event_id
    ) sub WHERE sub._rn = 1
),
traced AS (
    SELECT sub.target, sub.port, sub.trace_status, sub.trace_note
    FROM (
        SELECT target, COALESCE(port, '') AS port,
               CASE WHEN traced_at >= NOW() - make_interval(days => $%d) THEN 'active' ELSE 'expired' END AS trace_status,
               note AS trace_note,
               ROW_NUMBER() OVER (PARTITION BY UPPER(target), COALESCE(port, '') ORDER BY traced_at DESC) AS _rn
        FROM traced_targets
    ) sub WHERE sub._rn = 1
),
device_tag_names AS (
    SELECT dt.device_id,
           json_agg(json_build_object('id', t.id, 'name', t.name, 'color', t.color)) AS tags_json,
           COUNT(*) AS tag_count
    FROM device_tags dt
    JOIN tags t ON t.id = dt.tag_id
    WHERE (t.batch_id IS NULL OR EXISTS (
        SELECT 1 FROM tag_batches tb WHERE tb.id = t.batch_id AND tb.status = 'active'
    ))
    GROUP BY dt.device_id
),
scored AS (
    SELECT
        a.id, a.device_id, a.source_ip, a.target, a.port,
        a.threat_type, a.threat_level, a.std_apt_org, a.apt_org, a.apt_org_tier,
        a.vendors, a.protocol, a.intel_tags, a.analysis_status, a.is_focused,
        a.alert_count, a.first_alert_time, a.last_alert_time,
        COALESCE(h.target_alert_count, 1) AS heat_target_alert_count,
        COALESCE(h.target_device_count, 1) AS heat_target_device_count,
        COALESCE(sih.source_ip_alert_count, 1) AS heat_source_ip_alert_count,
        COALESCE(dh.device_alert_count, 1) AS heat_device_alert_count,
        COALESCE(dh.device_alert_count, 1) AS device_id_count,
        e.event_id, e.event_name, e.event_status, e.event_color,
        CASE WHEN e.event_id IS NOT NULL AND EXISTS (
            SELECT 1 FROM mined_event_devices med WHERE med.event_id = e.event_id AND UPPER(med.device_id) = UPPER(a.device_id)
        ) THEN 1 ELSE 0 END AS event_device_match,
        tr.trace_status, tr.trace_note,
        COALESCE(dtn.tags_json, '[]'::json) AS device_tags_json,
        dtn.tag_count,
        (
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
            CASE WHEN LOWER(COALESCE(a.threat_level,'')) IN ('critical','high','高') THEN 18
                 WHEN LOWER(COALESCE(a.threat_level,'')) IN ('medium','中') THEN 8
                 WHEN LOWER(COALESCE(a.threat_level,'')) IN ('low','低') THEN 3
                 ELSE 0 END +
            CASE WHEN LOWER(COALESCE(a.apt_org_tier,'')) IN ('s','s级','a','a级','high','高') THEN 16
                 WHEN LOWER(COALESCE(a.apt_org_tier,'')) IN ('b','b级','medium','中') THEN 10
                 ELSE 6 END +
            LEAST(COALESCE(h.target_alert_count, 1) * 2, 18) +
            LEAST(COALESCE(h.target_device_count, 1) * 6, 24) +
            LEAST(COALESCE(sih.source_ip_alert_count, 1) * 2, 14) +
            LEAST(COALESCE(dh.device_alert_count, 1), 10) +
            CASE WHEN cardinality(string_to_array(NULLIF(COALESCE(a.vendors,''), ''), ',')) >= 2
                 THEN LEAST(cardinality(string_to_array(NULLIF(COALESCE(a.vendors,''), ''), ',')) * 3, 9)
                 ELSE 0 END +
            CASE WHEN e.event_name IS NOT NULL THEN 6 ELSE 0 END +
            CASE WHEN tr.trace_status = 'active' THEN -12
                 WHEN tr.trace_status IS NOT NULL THEN -4
                 ELSE 0 END +
            LEAST(COALESCE(dtn.tag_count, 0) * 2, 8)
        ) AS candidate_score
    FROM base a
    LEFT JOIN heat h ON a.device_id = h.device_id AND a.target = h.target
    LEFT JOIN source_ip_heat sih ON a.source_ip = sih.source_ip
    LEFT JOIN device_heat dh ON a.device_id = dh.device_id
    LEFT JOIN events e ON UPPER(e.target) = UPPER(a.target)
        AND (e.port IN ('', '*') OR e.port = COALESCE(a.port, ''))
    LEFT JOIN traced tr ON UPPER(tr.target) = UPPER(a.target) AND (tr.port IN ('', COALESCE(a.port, '')))
    LEFT JOIN device_tag_names dtn ON UPPER(dtn.device_id) = UPPER(a.device_id)
)
SELECT json_build_object(
    'id', id,
    'device_id', device_id,
    'source_ip', source_ip,
    'target', target,
    'port', port,
    'threat_type', threat_type,
    'threat_level', threat_level,
    'std_apt_org', std_apt_org,
    'apt_org', apt_org,
    'apt_org_tier', apt_org_tier,
    'vendors', vendors,
    'protocol', protocol,
    'intel_tags', intel_tags,
    'analysis_status', analysis_status,
    'is_focused', is_focused,
    'alert_count', alert_count,
    'first_alert_time', to_char(first_alert_time, 'YYYY-MM-DD HH24:MI:SS'),
    'last_alert_time', to_char(last_alert_time, 'YYYY-MM-DD HH24:MI:SS'),
    'heat_target_alert_count', heat_target_alert_count,
    'heat_target_device_count', heat_target_device_count,
    'heat_source_ip_alert_count', heat_source_ip_alert_count,
    'heat_device_alert_count', heat_device_alert_count,
    'device_id_count', heat_device_alert_count,
    'event_id', event_id,
    'event_name', event_name,
    'event_status', event_status,
    'event_color', event_color,
    'event_device_match', event_device_match,
    'trace_status', trace_status,
    'trace_note', trace_note,
    'device_tags_json', device_tags_json,
    'candidate_score', candidate_score,
    'source_ip_count', heat_source_ip_alert_count
) AS row_json
FROM scored
ORDER BY %s %s, id %s
LIMIT $%d OFFSET $%d
`, whereSQL, argIdx, sortField, sortOrder, sortOrder, argIdx+1, argIdx+2)

	args = append(args, traceTTL)
	args = append(args, p.PageSize, (p.Page-1)*p.PageSize)

	rows, err := r.DB.Query(query, args...)
	if err != nil {
		return nil, 0, fmt.Errorf("query candidates: %w", err)
	}
	defer rows.Close()

	results := make([]CandidateRow, 0)
	for rows.Next() {
		var jsonStr string
		if err := rows.Scan(&jsonStr); err != nil {
			return nil, 0, fmt.Errorf("scan row: %w", err)
		}
		var row CandidateRow
		if err := json.Unmarshal([]byte(jsonStr), &row); err != nil {
			return nil, 0, fmt.Errorf("unmarshal row: %w, json: %s", err, jsonStr[:min(200, len(jsonStr))])
		}
		results = append(results, row)
	}

	// COUNT 查询（不需要 traceTTL 参数）
	countQuery := fmt.Sprintf("SELECT COUNT(*) FROM alerts a WHERE %s", whereSQL)
	countArgs := args[:nWhereArgs] // only WHERE clause args (traceTTL/pageSize/offset not needed)
	var total int64
	if err := r.DB.QueryRow(countQuery, countArgs...).Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("count candidates: %w", err)
	}

	return results, total, nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// GetAlerts 查询告警列表（使用 json_build_object 避免类型问题）
func (r *CandidateRepo) GetAlerts(p *CandidateQueryParams) ([]map[string]interface{}, int64, error) {
	whereSQL, args, argIdx := BuildWhereSQL(p)

	sortField := "first_alert_time"
	sortOrder := "DESC"
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
	if strings.ToLower(p.SortOrder) == "asc" {
		sortOrder = "ASC"
	}

	// 使用 json_build_object 返回每行
	query := fmt.Sprintf("SELECT json_build_object(%s) AS row_json FROM alerts a WHERE %s ORDER BY a.%s %s LIMIT $%d OFFSET $%d",
		alertColumnsSQL(), whereSQL, sortField, sortOrder, argIdx, argIdx+1)
	args = append(args, p.PageSize, (p.Page-1)*p.PageSize)

	rows, err := r.DB.Query(query, args...)
	if err != nil {
		return nil, 0, fmt.Errorf("query alerts: %w", err)
	}
	defer rows.Close()

	results := make([]map[string]interface{}, 0)
	for rows.Next() {
		var jsonStr string
		if err := rows.Scan(&jsonStr); err != nil {
			return nil, 0, fmt.Errorf("scan: %w", err)
		}
		var row map[string]interface{}
		if err := json.Unmarshal([]byte(jsonStr), &row); err != nil {
			return nil, 0, fmt.Errorf("unmarshal: %w", err)
		}
		results = append(results, row)
	}

	// COUNT
	countQuery := fmt.Sprintf("SELECT COUNT(*) FROM alerts a WHERE %s", whereSQL)
	var total int64
	r.DB.QueryRow(countQuery, args[:len(args)-2]...).Scan(&total)

	return results, total, nil
}

// alertColumnsSQL 生成 json_build_object 的列定义
func alertColumnsSQL() string {
	cols := []string{
		"'id', id", "'device_id', device_id", "'source_ip', source_ip",
		"'target', target", "'port', port", "'threat_type', threat_type",
		"'threat_level', threat_level", "'std_apt_org', std_apt_org",
		"'apt_org', apt_org", "'apt_org_tier', apt_org_tier",
		"'alert_count', alert_count", "'vendors', vendors",
		"'protocol', protocol", "'intel_tags', intel_tags",
		"'dns_resolved_ip', dns_resolved_ip", "'asset_type', asset_type",
		"'source_file', source_file", "'analysis_status', analysis_status",
		"'is_focused', is_focused",
		"'first_alert_time', to_char(first_alert_time, 'YYYY-MM-DD HH24:MI:SS')",
		"'last_alert_time', to_char(last_alert_time, 'YYYY-MM-DD HH24:MI:SS')",
		"'imported_at', to_char(imported_at, 'YYYY-MM-DD HH24:MI:SS')",
	}
	return strings.Join(cols, ", ")
}

// GetFilterOptions 获取筛选选项
func (r *CandidateRepo) GetFilterOptions() (map[string][]string, error) {
	options := make(map[string][]string)

	// 威胁类型
	threatTypes := make([]string, 0)
	typeStrRows, _ := r.DB.Query("SELECT DISTINCT threat_type FROM alerts WHERE threat_type IS NOT NULL AND threat_type != '' ORDER BY threat_type")
	defer typeStrRows.Close()
	for typeStrRows.Next() {
		var v string
		typeStrRows.Scan(&v)
		threatTypes = append(threatTypes, v)
	}
	options["threat_type"] = threatTypes

	// 威胁等级
	threatLevels := make([]string, 0)
	levelRows, _ := r.DB.Query("SELECT DISTINCT threat_level FROM alerts WHERE threat_level IS NOT NULL AND threat_level != '' ORDER BY threat_level")
	defer levelRows.Close()
	for levelRows.Next() {
		var v string
		levelRows.Scan(&v)
		threatLevels = append(threatLevels, v)
	}
	options["threat_level"] = threatLevels

	// 端口
	ports := make([]string, 0)
	portRows, _ := r.DB.Query("SELECT DISTINCT port FROM alerts WHERE port IS NOT NULL AND port != '' ORDER BY port")
	defer portRows.Close()
	for portRows.Next() {
		var v string
		portRows.Scan(&v)
		ports = append(ports, v)
	}
	options["port"] = ports

	// 标准APT组织
	stdAptOrgs := make([]string, 0)
	aptOrgRows, _ := r.DB.Query("SELECT DISTINCT std_apt_org FROM alerts WHERE std_apt_org IS NOT NULL AND std_apt_org != '' ORDER BY std_apt_org")
	defer aptOrgRows.Close()
	for aptOrgRows.Next() {
		var v string
		aptOrgRows.Scan(&v)
		stdAptOrgs = append(stdAptOrgs, v)
	}
	options["std_apt_org"] = stdAptOrgs

	// 设备ID
	deviceIDs := make([]string, 0)
	deviceRows, _ := r.DB.Query("SELECT DISTINCT device_id FROM alerts WHERE device_id IS NOT NULL AND device_id != '' ORDER BY device_id")
	defer deviceRows.Close()
	for deviceRows.Next() {
		var v string
		deviceRows.Scan(&v)
		deviceIDs = append(deviceIDs, v)
	}
	options["device_id"] = deviceIDs

	// 源IP
	sourceIPs := make([]string, 0)
	ipRows, _ := r.DB.Query("SELECT DISTINCT source_ip FROM alerts WHERE source_ip IS NOT NULL AND source_ip != '' ORDER BY source_ip")
	defer ipRows.Close()
	for ipRows.Next() {
		var v string
		ipRows.Scan(&v)
		sourceIPs = append(sourceIPs, v)
	}
	options["source_ip"] = sourceIPs

	// 设备标签名称
	tagNames := make([]string, 0)
	tagRows, _ := r.DB.Query(`
		SELECT DISTINCT t.name
		FROM tags t
		INNER JOIN device_tags dt ON dt.tag_id = t.id
		WHERE (t.batch_id IS NULL OR EXISTS (
			SELECT 1 FROM tag_batches tb WHERE tb.id = t.batch_id AND tb.status = 'active'
		))
		ORDER BY t.name
	`)
	defer tagRows.Close()
	for tagRows.Next() {
		var v string
		tagRows.Scan(&v)
		tagNames = append(tagNames, v)
	}
	options["device_tags"] = tagNames

	// priority: fixed three values (matches 3.x baseline)
	options["priority"] = []string{"高优先", "中优先", "观察"}

	// badges: union of all badge labels from enabled badges config
	badgeLabels := make([]string, 0)
	for _, badgeName := range r.getEnabledBadgeLabels() {
		badgeLabels = append(badgeLabels, badgeName)
	}
	options["badges"] = badgeLabels

	// ioc_note: text input filter, no options list
	options["ioc_note"] = nil

	return options, nil
}

func (r *CandidateRepo) GetIocDevices(dateStart, dateEnd, target, port string) (*IocDevicesResponse, error) {
	args := []interface{}{strings.TrimSpace(target)}
	conds := []string{"UPPER(a.target) = UPPER($1)"}
	argIdx := 2

	if strings.TrimSpace(port) != "" {
		conds = append(conds, fmt.Sprintf("COALESCE(a.port, '') = $%d", argIdx))
		args = append(args, strings.TrimSpace(port))
		argIdx++
	} else {
		conds = append(conds, "COALESCE(a.port, '') = ''")
	}
	if strings.TrimSpace(dateStart) != "" {
		conds = append(conds, fmt.Sprintf("a.first_alert_time >= $%d", argIdx))
		args = append(args, strings.TrimSpace(dateStart))
		argIdx++
	}
	if strings.TrimSpace(dateEnd) != "" {
		conds = append(conds, fmt.Sprintf("a.first_alert_time < ($%d::date + interval '1 day')", argIdx))
		args = append(args, strings.TrimSpace(dateEnd))
		argIdx++
	}

	query := fmt.Sprintf(`
WITH matched_devices AS (
    SELECT DISTINCT UPPER(a.device_id) AS device_id
    FROM alerts a
    WHERE %s
      AND COALESCE(a.device_id, '') != ''
),
device_tag_names AS (
    SELECT
        UPPER(dt.device_id) AS device_id,
        json_agg(json_build_object('id', t.id, 'name', t.name, 'color', t.color) ORDER BY t.name) AS tags_json
    FROM device_tags dt
    JOIN tags t ON t.id = dt.tag_id
    WHERE (t.batch_id IS NULL OR EXISTS (
        SELECT 1 FROM tag_batches tb WHERE tb.id = t.batch_id AND tb.status = 'active'
    ))
    GROUP BY UPPER(dt.device_id)
)
SELECT md.device_id, COALESCE(dtn.tags_json, '[]'::json)
FROM matched_devices md
LEFT JOIN device_tag_names dtn ON dtn.device_id = md.device_id
ORDER BY md.device_id
`, strings.Join(conds, " AND "))

	rows, err := r.DB.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("query ioc devices: %w", err)
	}
	defer rows.Close()

	resp := &IocDevicesResponse{Items: []IocDeviceItem{}}
	for rows.Next() {
		var item IocDeviceItem
		var tagsRaw json.RawMessage
		if err := rows.Scan(&item.DeviceID, &tagsRaw); err != nil {
			return nil, fmt.Errorf("scan ioc device: %w", err)
		}
		if len(tagsRaw) > 0 {
			if err := json.Unmarshal(tagsRaw, &item.Tags); err != nil {
				return nil, fmt.Errorf("parse ioc device tags: %w", err)
			}
		}
		resp.Items = append(resp.Items, item)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate ioc devices: %w", err)
	}
	return resp, nil
}

// getEnabledBadgeLabels returns badge labels for enabled badges.
func (r *CandidateRepo) getEnabledBadgeLabels() []string {
	// Badge labels for all 9 badge types (order doesn't matter)
	return []string{
		"APT词典", "高级黑灰产", "噪声家族", "多厂商",
		"跨天持续", "横向扩散", "追踪过期", "高级别", "疑似扫描",
	}
}

// GetCrossDayPairs returns set of (source_ip, target) pairs that span multiple days.
// Used for cross_day badge computation.
func (r *CandidateRepo) GetCrossDayPairs(p *CandidateQueryParams) (map[string]bool, error) {
	pairs := make(map[string]bool)
	dateFilter := "1=1"
	args := []interface{}{}
	if p.DateStart != "" || p.DateEnd != "" {
		conds := []string{}
		if p.DateStart != "" {
			conds = append(conds, fmt.Sprintf("first_alert_time >= $%d", len(args)+1))
			args = append(args, p.DateStart)
		}
		if p.DateEnd != "" {
			conds = append(conds, fmt.Sprintf("first_alert_time < ($%d::date + interval '1 day')", len(args)+1))
			args = append(args, p.DateEnd)
		}
		dateFilter = strings.Join(conds, " AND ")
	}

	query := fmt.Sprintf(`
		SELECT source_ip, target FROM alerts WHERE %s
		GROUP BY source_ip, target
		HAVING COUNT(DISTINCT DATE(first_alert_time)) > 1
	`, dateFilter)

	rows, err := r.DB.Query(query, args...)
	if err != nil {
		return pairs, fmt.Errorf("query cross_day pairs: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var sip, target string
		if err := rows.Scan(&sip, &target); err == nil {
			pairs[sip+"||"+target] = true
		}
	}
	return pairs, nil
}

// GetLateralIPs returns set of source_ips that connect to >= N distinct targets.
// Used for lateral badge computation.
func (r *CandidateRepo) GetLateralIPs(p *CandidateQueryParams, threshold int) (map[string]bool, error) {
	ips := make(map[string]bool)
	dateFilter := "1=1"
	args := []interface{}{}
	if p.DateStart != "" || p.DateEnd != "" {
		conds := []string{}
		if p.DateStart != "" {
			conds = append(conds, fmt.Sprintf("first_alert_time >= $%d", len(args)+1))
			args = append(args, p.DateStart)
		}
		if p.DateEnd != "" {
			conds = append(conds, fmt.Sprintf("first_alert_time < ($%d::date + interval '1 day')", len(args)+1))
			args = append(args, p.DateEnd)
		}
		dateFilter = strings.Join(conds, " AND ")
	}

	query := fmt.Sprintf(`
		SELECT source_ip FROM alerts WHERE %s
		GROUP BY source_ip
		HAVING COUNT(DISTINCT target) >= $%d
	`, dateFilter, len(args)+1)
	args = append(args, threshold)

	rows, err := r.DB.Query(query, args...)
	if err != nil {
		return ips, fmt.Errorf("query lateral IPs: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var sip string
		if err := rows.Scan(&sip); err == nil {
			ips[sip] = true
		}
	}
	return ips, nil
}
