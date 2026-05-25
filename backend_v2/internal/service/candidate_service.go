package service

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"apt-mining-platform/v2/internal/config"
	"apt-mining-platform/v2/internal/model"
	"apt-mining-platform/v2/internal/repository"

	"gopkg.in/yaml.v3"
)

type CandidateService struct {
	Repo   *repository.CandidateRepo
	Config *config.Config
}

// BadgeContext 预计算的跨行 Badge 数据
type BadgeContext struct {
	CrossDayPairs map[string]bool
	LateralIPs     map[string]bool
}

func NewCandidateService(repo *repository.CandidateRepo, cfg *config.Config) *CandidateService {
	return &CandidateService{Repo: repo, Config: cfg}
}

// QueryCandidates 查询候选结果
func (s *CandidateService) QueryCandidates(p *repository.CandidateQueryParams) (*model.CandidateResponse, error) {
	// When badge filtering is active, fetch more rows from SQL to ensure
	// enough items remain after filtering (since badges are computed in Go)
	effectivePageSize := p.PageSize
	if len(p.BadgesFilter) > 0 {
		effectivePageSize = p.PageSize * 10
		if effectivePageSize > 100000 {
			effectivePageSize = 100000
		}
		// Create a copy of params with increased page size
		origPageSize := p.PageSize
		p.PageSize = effectivePageSize
		rows, total, err := s.repoQueryWithBadgeFilter(p, origPageSize)
		if err != nil {
			return nil, fmt.Errorf("query: %w", err)
		}
		filterOptions, _ := s.Repo.GetFilterOptions()
		return &model.CandidateResponse{
			Items:         rows,
			Total:         total,
			Page:          p.Page,
			PageSize:      origPageSize,
			Meta: model.ResponseMeta{
				PlatformScope:         "all_alerts",
				CandidateScope:        "scored_and_sorted",
				DifferencesFromScript: "none",
			},
			FilterOptions: filterOptions,
		}, nil
	}

	rows, total, err := s.Repo.QueryCandidates(p)
	if err != nil {
		return nil, fmt.Errorf("query: %w", err)
	}

	// Pre-compute cross-row badge data (single SQL each)
	crossDayPairs, _ := s.Repo.GetCrossDayPairs(p)
	lateralIPs, _ := s.Repo.GetLateralIPs(p, s.Config.Badges.Thresholds.LateralMinTargets)

	badgeCtx := BadgeContext{
		CrossDayPairs: crossDayPairs,
		LateralIPs:    lateralIPs,
	}

	items := make([]model.CandidateItem, 0, len(rows))
	for _, row := range rows {
		item := s.rowToItem(row, badgeCtx)
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

// repoQueryWithBadgeFilter queries with increased page size, then filters by badge.
func (s *CandidateService) repoQueryWithBadgeFilter(p *repository.CandidateQueryParams, actualPageSize int) ([]model.CandidateItem, int64, error) {
	rows, _, err := s.Repo.QueryCandidates(p)
	if err != nil {
		return nil, 0, err
	}

	crossDayPairs, _ := s.Repo.GetCrossDayPairs(p)
	lateralIPs, _ := s.Repo.GetLateralIPs(p, s.Config.Badges.Thresholds.LateralMinTargets)

	badgeCtx := BadgeContext{
		CrossDayPairs: crossDayPairs,
		LateralIPs:    lateralIPs,
	}

	// Convert rows to items
	allItems := make([]model.CandidateItem, 0, len(rows))
	for _, row := range rows {
		item := s.rowToItem(row, badgeCtx)
		allItems = append(allItems, item)
	}

	// Filter by badge (match by name or label)
	filtered := make([]model.CandidateItem, 0, len(allItems))
	for _, item := range allItems {
		for _, badge := range item.Badges {
			if matchesBadgeFilter(badge, p.BadgesFilter) {
				filtered = append(filtered, item)
				break
			}
		}
	}

	// Compute effective total for pagination
	filteredTotal := int64(len(filtered))

	// Slice to page
	start := (p.Page - 1) * actualPageSize
	if start >= len(filtered) {
		return []model.CandidateItem{}, filteredTotal, nil
	}
	end := start + actualPageSize
	if end > len(filtered) {
		end = len(filtered)
	}

	return filtered[start:end], filteredTotal, nil
}

// matchesBadgeFilter checks if a badge matches the filter by name or label.
func matchesBadgeFilter(badge model.Badge, filter []string) bool {
	for _, f := range filter {
		fLower := strings.ToLower(f)
		if strings.ToLower(badge.Name) == fLower || strings.ToLower(badge.Label) == fLower {
			return true
		}
	}
	return false
}

// rowToItem 将强类型 CandidateRow 转换为 API 响应结构
func (s *CandidateService) rowToItem(row repository.CandidateRow, badgeCtx BadgeContext) model.CandidateItem {
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
	item.TargetKindLabel = targetKindLabel(item.TargetKind)

	// 追踪状态中文
	item.TraceStatusLabel = traceStatusLabel(item.TraceStatus)

	// 设备标签摘要
	item.DeviceNoteSummary = deviceNoteSummary(row.DeviceTagsJSON)

	// 热度摘要
	item.HeatSummary = heatSummary(row)

	// Badge 计算
	item.Badges = s.computeBadges(row, badgeCtx)

	// 命中规则
	item.CandidateRuleIDs = s.computeRuleIDs(row)

	// 命中原因
	item.CandidateReasons = append(item.CandidateReasons, s.computeReasons(row)...)

	// 设备标签
	item.DeviceTags = s.parseDeviceTags(row.DeviceTagsJSON)

	return item
}

// computeBadges 根据行数据计算徽章
func (s *CandidateService) computeBadges(row repository.CandidateRow, badgeCtx BadgeContext) []model.Badge {
	badges := make([]model.Badge, 0)
	enabled := GetEnabledBadges(s.Config)

	if enabled["apt_dict"] && row.StdAptOrg != "" {
		// Check against APT dictionary keys for a proper match
		aptDict := config.GetDict(s.Config.Paths.DictAPT)
		if len(aptDict) > 0 {
			for _, org := range strings.Split(row.StdAptOrg, ",") {
				org = strings.ToLower(strings.TrimSpace(org))
				if _, ok := aptDict[org]; ok {
					badges = append(badges, model.Badge{Name: "apt_dict", Label: "APT词典", Color: "red"})
					break
				}
			}
		} else {
			// Fallback: if dict is empty or not loaded, fall back to non-empty check
			badges = append(badges, model.Badge{Name: "apt_dict", Label: "APT词典", Color: "red"})
		}
	}
	if enabled["advanced_crime"] && row.AptOrg != "" {
		crimeKeywords := getCrimeKeywords(s.Config.Paths.DictCrime)
		if len(crimeKeywords) > 0 {
			for _, org := range strings.Split(row.AptOrg, ",") {
				org = strings.TrimSpace(org)
				orgLower := strings.ToLower(org)
				for _, kw := range crimeKeywords {
					if orgLower == strings.ToLower(kw) || strings.Contains(orgLower, strings.ToLower(kw)) {
						badges = append(badges, model.Badge{Name: "advanced_crime", Label: "高级黑灰产", Color: "purple"})
						break
					}
				}
			}
		}
	}
	if enabled["noise_family"] && row.ThreatType != "" {
		noiseDict := config.GetDict(s.Config.Paths.DictNoise)
		if len(noiseDict) > 0 {
			for _, tag := range strings.Split(row.ThreatType, ",") {
				tag = strings.ToLower(strings.TrimSpace(tag))
				if _, ok := noiseDict[tag]; ok {
					badges = append(badges, model.Badge{Name: "noise_family", Label: "噪声家族", Color: "gray"})
					break
				}
			}
		} else {
			// Fallback to keyword matching
			if IsNoiseFamily(row.ThreatType, "") {
				badges = append(badges, model.Badge{Name: "noise_family", Label: "噪声家族", Color: "gray"})
			}
		}
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
	// expired_revive: check if trace_status is 'expired' (SQL already computes this)
	if enabled["expired_revive"] && row.TraceStatus != nil && *row.TraceStatus == "expired" {
		badges = append(badges, model.Badge{Name: "expired_revive", Label: "追踪过期", Color: "orange"})
	}
	// cross_day: source_ip+target pair spans multiple days
	if enabled["cross_day"] && badgeCtx.CrossDayPairs != nil {
		key := row.SourceIP + "||" + row.Target
		if badgeCtx.CrossDayPairs[key] {
			badges = append(badges, model.Badge{Name: "cross_day", Label: "跨天持续", Color: "green"})
		}
	}
	// lateral: source_ip connects to >= N distinct targets
	if enabled["lateral"] && badgeCtx.LateralIPs != nil {
		if badgeCtx.LateralIPs[row.SourceIP] {
			badges = append(badges, model.Badge{Name: "lateral", Label: "横向扩散", Color: "blue"})
		}
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

// getCrimeKeywords reads the crime YAML file and extracts all organization names and aliases.
// The YAML uses "organizations: [{canonical, aliases}]" format.
var crimeKeywordCache []string

func getCrimeKeywords(crimePath string) []string {
	if len(crimeKeywordCache) > 0 {
		return crimeKeywordCache
	}

	type OrgEntry struct {
		Canonical string   `yaml:"canonical"`
		Aliases   []string `yaml:"aliases"`
	}
	var data struct {
		Organizations []OrgEntry `yaml:"organizations"`
	}

	absPath := config.ResolvePath(crimePath)
	content, err := os.ReadFile(absPath)
	if err != nil {
		return nil
	}
	if err := yaml.Unmarshal(content, &data); err != nil {
		return nil
	}

	for _, org := range data.Organizations {
		if org.Canonical != "" {
			crimeKeywordCache = append(crimeKeywordCache, org.Canonical)
		}
		crimeKeywordCache = append(crimeKeywordCache, org.Aliases...)
	}
	return crimeKeywordCache
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

func targetKindLabel(kind string) string {
	switch kind {
	case "ip":
		return "IP"
	case "domain":
		return "域名"
	default:
		return "其他"
	}
}

func traceStatusLabel(status *string) string {
	if status == nil {
		return ""
	}
	switch *status {
	case "active":
		return "追踪中"
	case "expired":
		return "追踪过期"
	default:
		return ""
	}
}

func deviceNoteSummary(raw []byte) string {
	if len(raw) == 0 || string(raw) == "null" {
		return ""
	}
	var tags []model.DeviceTag
	if err := json.Unmarshal(raw, &tags); err != nil {
		return ""
	}
	names := make([]string, 0, len(tags))
	for _, t := range tags {
		names = append(names, t.Name)
	}
	return strings.Join(names, ", ")
}

func heatSummary(row repository.CandidateRow) string {
	parts := []string{}
	if row.HeatTargetDeviceCount > 1 {
		parts = append(parts, fmt.Sprintf("%d台设备", row.HeatTargetDeviceCount))
	}
	if row.HeatTargetAlertCount > 1 {
		parts = append(parts, fmt.Sprintf("%d条告警", row.HeatTargetAlertCount))
	}
	if row.HeatSourceIPAlertCnt > 1 {
		parts = append(parts, fmt.Sprintf("%d个源IP", row.HeatSourceIPAlertCnt))
	}
	if len(parts) == 0 {
		return ""
	}
	return strings.Join(parts, " / ")
}
