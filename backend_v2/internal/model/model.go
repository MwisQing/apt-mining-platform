package model

import "time"

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

// PriorityInfo 优先级
type PriorityInfo struct {
	ID    string `json:"id"`
	Label string `json:"label"`
	Rank  int    `json:"rank"`
}

// EventInfo 事件摘要（嵌入候选响应）
type EventInfo struct {
	ID   int    `json:"id"`
	Name string `json:"event_name"`
	Color string `json:"color"`
	Status string `json:"status"`
}

// CandidateItem 候选行（API 响应）
type CandidateItem struct {
	ID                int            `json:"id"`
	DeviceID          string         `json:"device_id"`
	SourceIP          string         `json:"source_ip"`
	Target            string         `json:"target"`
	Port              string         `json:"port"`
	ThreatType        string         `json:"threat_type"`
	ThreatLevel       string         `json:"threat_level"`
	StdAptOrg         string         `json:"std_apt_org"`
	AptOrg            string         `json:"apt_org"`
	AptOrgTier        string         `json:"apt_org_tier"`
	Vendors           string         `json:"vendors"`
	FirstAlertTime    string         `json:"first_alert_time"`
	LastAlertTime     string         `json:"last_alert_time"`
	AlertCount        int            `json:"alert_count"`
	Badges            []Badge        `json:"badges"`
	CandidateRuleIDs  []string       `json:"candidate_rule_ids"`
	CandidateReasons  []string       `json:"candidate_reasons"`
	CandidateScore    int            `json:"candidate_score"`
	CandidatePriority PriorityInfo   `json:"candidate_priority"`
	TargetKind        string         `json:"target_kind"`
	Heat              HeatInfo       `json:"heat"`
	DeviceTags        []DeviceTag    `json:"device_tags"`
	TraceStatus       *string        `json:"trace_status"`
	EventStatus       *string        `json:"event_status"`
	Event             *EventInfo     `json:"event"`
	DeviceEvent       *EventInfo     `json:"device_event"`
	IocNote           string         `json:"ioc_note"`
	AnalysisStatus    string         `json:"analysis_status"`
	IsFocused         bool           `json:"is_focused"`
	SourceIPCount     int            `json:"source_ip_count"`
	DeviceIDCount     int            `json:"device_id_count"`
	TargetKindLabel   string         `json:"target_kind_label"`
	TraceStatusLabel  string         `json:"trace_status_label"`
	DeviceNoteSummary string         `json:"device_note_summary"`
	HeatSummary       string         `json:"heat_summary"`
}

// CandidateResponse 候选 API 响应
type CandidateResponse struct {
	Items         []CandidateItem      `json:"items"`
	Total         int64                `json:"total"`
	Page          int                  `json:"page"`
	PageSize      int                  `json:"page_size"`
	Meta          ResponseMeta         `json:"meta"`
	FilterOptions map[string][]string  `json:"filter_options,omitempty"`
}

// ResponseMeta 响应元数据
type ResponseMeta struct {
	PlatformScope         string `json:"platform_scope"`
	CandidateScope        string `json:"candidate_scope"`
	DifferencesFromScript string `json:"differences_from_script"`
}

// Event 事件
type Event struct {
	ID      int       `json:"id"`
	Name    string    `json:"event_name"`
	Color   string    `json:"color"`
	Status  string    `json:"status"`
	MinedAt time.Time `json:"mined_at"`
	Note    string    `json:"note"`
}

// EventDetail 事件详情
type EventDetail struct {
	Event
	Devices   []string        `json:"devices"`
	IOCs      []EventIOC      `json:"iocs"`
	Followups []EventFollowup `json:"followups"`
}

// EventIOC 事件 IOC
type EventIOC struct {
	Target string `json:"target"`
	Port   string `json:"port"`
}

// EventFollowup 跟进记录
type EventFollowup struct {
	ID        int       `json:"id"`
	ActionType string    `json:"action_type"`
	CreatedAt time.Time `json:"created_at"`
	Note      string    `json:"note"`
}

// Tag 标签
type Tag struct {
	ID          int       `json:"id"`
	Name        string    `json:"name"`
	Color       string    `json:"color"`
	IsPermanent bool      `json:"is_permanent"`
	BatchID     *int      `json:"batch_id"`
	CreatedAt   time.Time `json:"created_at"`
	Note        string    `json:"note"`
}

// TagBatch 标签批次
type TagBatch struct {
	ID                int       `json:"id"`
	BatchName         string    `json:"batch_name"`
	CreatedAt         time.Time `json:"created_at"`
	Note              string    `json:"note"`
	Status            string    `json:"status"`
	DeviceIDsSnapshot []string  `json:"device_ids_snapshot"`
	TagName           string    `json:"tag_name"`
	Color             string    `json:"color"`
}

// ImportJob 导入任务
type ImportJob struct {
	ID           int       `json:"id"`
	SourceFile   string    `json:"source_file"`
	Status       string    `json:"status"`
	TotalRows    int       `json:"total_rows"`
	ParsedRows   int       `json:"parsed_rows"`
	RowsInserted int       `json:"rows_inserted"`
	RowsSkipped  int       `json:"rows_skipped"`
	RowsFailed   int       `json:"rows_failed"`
	Log          string    `json:"log"`
	FileHash     string    `json:"file_hash"`
	QueuePos     int       `json:"queue_position"`
	CreatedAt    time.Time `json:"imported_at"`
}

// ImportSheet Sheet 信息
type ImportSheet struct {
	ID          int    `json:"id"`
	ImportID    int    `json:"import_id"`
	SheetName   string `json:"sheet_name"`
	SheetIndex  int    `json:"sheet_index"`
	HeaderRow   *int   `json:"header_row"`
	HeadersJSON string `json:"headers_json"`
	RowCount    int    `json:"row_count"`
	ParsedRows  int    `json:"parsed_rows"`
	RawRows     int    `json:"raw_rows"`
	FailedRows  int    `json:"failed_rows"`
	Status      string `json:"status"`
	CreatedAt   string `json:"created_at"`
}

// TracedItem 追踪项
type TracedItem struct {
	ID       int    `json:"id"`
	Target   string `json:"target"`
	Port     string `json:"port"`
	TracedAt string `json:"traced_at"`
	Note     string `json:"note"`
}
