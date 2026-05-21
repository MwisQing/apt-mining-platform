package service

import (
	"encoding/json"
	"fmt"
	"strings"

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
func (s *CandidateService) QueryCandidates(p *repository.CandidateQueryParams) (*model.CandidateResponse, error) {
	rows, total, err := s.Repo.QueryCandidates(p)
	if err != nil {
		return nil, fmt.Errorf("query: %w", err)
	}

	items := make([]model.CandidateItem, 0, len(rows))
	for _, row := range rows {
		item := s.rowToItem(row)
		items = append(items, item)
	}

	filterOptions, _ := s.Repo.GetFilterOptions()

	return &model.CandidateResponse{
		Items:         items,
		Total:         total,
		Page:          p.Page,
		PageSize:      p.PageSize,
		Meta: model.ResponseMeta{
			PlatformScope:         "all_alerts",
			CandidateScope:        "scored_and_sorted",
			DifferencesFromScript: "none",
		},
		FilterOptions: filterOptions,
	}, nil
}

// rowToItem 将强类型 CandidateRow 转换为 API 响应结构
func (s *CandidateService) rowToItem(row repository.CandidateRow) model.CandidateItem {
	item := model.CandidateItem{
		ID:                int(row.ID),
		DeviceID:          row.DeviceID,
		SourceIP:          row.SourceIP,
		Target:            row.Target,
		Port:              row.Port,
		ThreatType:        row.ThreatType,
		ThreatLevel:       row.ThreatLevel,
		StdAptOrg:         row.StdAptOrg,
		AptOrg:            row.AptOrg,
		AptOrgTier:        row.AptOrgTier,
		Vendors:           row.Vendors,
		FirstAlertTime:    row.FirstAlertTime,
		LastAlertTime:     row.LastAlertTime,
		AlertCount:        row.AlertCount,
		AnalysisStatus:    row.AnalysisStatus,
		IsFocused:         row.IsFocused == 1,
		CandidateScore:    row.CandidateScore,
		SourceIPCount:     row.SourceIPCount,
		DeviceIDCount:     row.DeviceIDCount,
		Badges:            make([]model.Badge, 0),
		CandidateRuleIDs:  make([]string, 0),
		CandidateReasons:  make([]string, 0),
	}

	// 优先级
	item.CandidatePriority = classifyPriority(item.CandidateScore)

	// 热度
	item.Heat = model.HeatInfo{
		TargetAlertCount:   row.HeatTargetAlertCount,
		TargetDeviceCount:  row.HeatTargetDeviceCount,
		SourceIPAlertCount: row.HeatSourceIPAlertCnt,
		DeviceAlertCount:   row.HeatDeviceAlertCount,
	}

	// 事件信息
	if row.EventName != nil && *row.EventName != "" {
		item.CandidateReasons = append(item.CandidateReasons, "已关联事件:"+*row.EventName)
		eventID := int64(0)
		if row.EventID != nil {
			eventID = *row.EventID
		}
		eventInfo := &model.EventInfo{
			ID:   int(eventID),
			Name: *row.EventName,
			Color: row.EventColor,
			Status: "",
		}
		item.Event = eventInfo
		if row.EventStatus != nil && *row.EventStatus != "" {
			eventInfo.Status = *row.EventStatus
		}
		// 设备关联到事件时，设备标签列也显示事件
		if row.EventDeviceMatch == 1 {
			item.DeviceEvent = eventInfo
		}
	}
	if row.EventStatus != nil && *row.EventStatus != "" {
		es := *row.EventStatus
		item.EventStatus = &es
		if item.Event != nil {
			item.Event.Status = es
		}
	}

	// 追踪状态
	if row.TraceStatus != nil && *row.TraceStatus != "" {
		ts := *row.TraceStatus
		item.TraceStatus = &ts
	}

	// IOC备注
	item.IocNote = row.TraceNote

	// 目标类型分类
	item.TargetKind = classifyTargetKind(item.Target, item.ThreatType)

	// Badge 计算
	item.Badges = s.computeBadges(row)

	// 命中规则
	item.CandidateRuleIDs = s.computeRuleIDs(row)

	// 命中原因
	item.CandidateReasons = append(item.CandidateReasons, s.computeReasons(row)...)

	// 设备标签
	item.DeviceTags = s.parseDeviceTags(row.DeviceTagsJSON)

	return item
}

// computeBadges 根据行数据计算徽章
func (s *CandidateService) computeBadges(row repository.CandidateRow) []model.Badge {
	badges := make([]model.Badge, 0)
	enabled := GetEnabledBadges(s.Config)

	if enabled["apt_dict"] && row.StdAptOrg != "" {
		badges = append(badges, model.Badge{Name: "apt_dict", Label: "APT词典", Color: "red"})
	}
	if enabled["noise_family"] && row.ThreatType != "" && IsNoiseFamily(row.ThreatType, "") {
		badges = append(badges, model.Badge{Name: "noise_family", Label: "噪声家族", Color: "gray"})
	}
	if enabled["multi_vendor"] && VendorCount(row.Vendors) >= s.Config.Badges.Thresholds.MultiVendorMin {
		badges = append(badges, model.Badge{Name: "multi_vendor", Label: "多厂商", Color: "yellow"})
	}
	if enabled["high_tier"] && row.AptOrgTier == "一级" {
		badges = append(badges, model.Badge{Name: "high_tier", Label: "高级别", Color: "gold"})
	}
	if enabled["scan_noise"] && int64(row.AlertCount) > int64(s.Config.Badges.Thresholds.ScanNoiseCount) {
		badges = append(badges, model.Badge{Name: "scan_noise", Label: "疑似扫描", Color: "lightgray"})
	}

	return badges
}

func (s *CandidateService) computeRuleIDs(row repository.CandidateRow) []string {
	ruleIDs := make([]string, 0)
	tt := strings.ToLower(row.ThreatType)

	if strings.Contains(tt, "apt") {
		ruleIDs = append(ruleIDs, "threat_type_apt")
	}
	if strings.Contains(tt, "远控") || strings.Contains(tt, "remote") {
		ruleIDs = append(ruleIDs, "threat_type_remote_control")
	}
	if row.StdAptOrg != "" {
		ruleIDs = append(ruleIDs, "std_apt_org_present")
	}
	if row.AptOrg != "" {
		ruleIDs = append(ruleIDs, "apt_org_present")
	}
	it := strings.ToLower(row.IntelTags)
	if it != "" && (strings.Contains(it, "apt") || strings.Contains(it, "c2") ||
		strings.Contains(it, "远控") || strings.Contains(it, "remote")) {
		ruleIDs = append(ruleIDs, "intel_tags_c2_remote")
	}
	return ruleIDs
}

func (s *CandidateService) computeReasons(row repository.CandidateRow) []string {
	reasons := make([]string, 0)
	if row.ThreatLevel != "" {
		reasons = append(reasons, "威胁等级:"+row.ThreatLevel)
	}
	if row.AptOrgTier != "" {
		reasons = append(reasons, "APT分级:"+row.AptOrgTier)
	}
	if vc := VendorCount(row.Vendors); vc >= 2 {
		reasons = append(reasons, fmt.Sprintf("多厂商同时命中(%d)", vc))
	}
	if row.HeatTargetDeviceCount >= 2 {
		reasons = append(reasons, fmt.Sprintf("同目标涉及 %d 台设备", row.HeatTargetDeviceCount))
	}
	if row.HeatTargetAlertCount >= 2 {
		reasons = append(reasons, fmt.Sprintf("目标热度:%d 条", row.HeatTargetAlertCount))
	}
	if row.HeatSourceIPAlertCnt >= 2 {
		reasons = append(reasons, fmt.Sprintf("源IP热度:%d 条", row.HeatSourceIPAlertCnt))
	}
	if row.HeatDeviceAlertCount >= 2 {
		reasons = append(reasons, fmt.Sprintf("设备热度:%d 条", row.HeatDeviceAlertCount))
	}
	return reasons
}

func (s *CandidateService) parseDeviceTags(raw []byte) []model.DeviceTag {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var tags []model.DeviceTag
	// raw is already json.RawMessage, just unmarshal
	if err := unmarshalJSON(raw, &tags); err != nil {
		return nil
	}
	return tags
}

func unmarshalJSON(data []byte, v interface{}) error {
	return json.Unmarshal(data, v)
}

func classifyPriority(score int) model.PriorityInfo {
	if score >= 110 {
		return model.PriorityInfo{ID: "p1", Label: "高优先", Rank: 3}
	}
	if score >= 75 {
		return model.PriorityInfo{ID: "p2", Label: "中优先", Rank: 2}
	}
	return model.PriorityInfo{ID: "p3", Label: "观察", Rank: 1}
}

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
