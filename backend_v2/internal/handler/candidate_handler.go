package handler

import (
	"encoding/csv"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

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
	p := &repository.CandidateQueryParams{
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

	if dt := c.Query("device_tags"); dt != "" {
		p.DeviceTags = splitCSV(dt)
	}
	if did := c.Query("device_ids"); did != "" {
		p.DeviceIDs = splitCSV(did)
	}
	if tt := c.Query("threat_types"); tt != "" {
		p.ThreatTypes = splitCSV(tt)
	}
	if tl := c.Query("threat_levels"); tl != "" {
		p.ThreatLevels = splitCSV(tl)
	}
	if at := c.Query("apt_tiers"); at != "" {
		p.AptTiers = splitCSV(at)
	}
	if ao := c.Query("apt_orgs"); ao != "" {
		p.AptOrgs = splitCSV(ao)
	}
	if pt := c.Query("ports"); pt != "" {
		p.Ports = splitCSV(pt)
	}
	if et := c.Query("exclude_device_tags"); et != "" {
		p.ExcludeTags = splitCSV(et)
	}
	if bf := c.Query("badges_filter"); bf != "" {
		p.BadgesFilter = splitCSV(bf)
	}

	p.HideTraced = parseBool(c.Query("hide_traced"), h.Service.Config.Rules.DefaultHideTraced)
	p.HideClosed = parseBool(c.Query("hide_closed"), h.Service.Config.Rules.DefaultHideClosedEvts)

	resp, err := h.Service.QueryCandidates(p)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, resp)
}

type AlertHandler struct {
	Repo *repository.CandidateRepo
}

func NewAlertHandler(repo *repository.CandidateRepo) *AlertHandler {
	return &AlertHandler{Repo: repo}
}

// ListAlerts GET /api/alerts
func (h *AlertHandler) ListAlerts(c *gin.Context) {
	p := &repository.CandidateQueryParams{
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

	items, total, err := h.Repo.GetAlerts(p)
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

// ExportAlerts POST /api/alerts/export
func (h *AlertHandler) ExportAlerts(c *gin.Context) {
	p := &repository.CandidateQueryParams{
		DateStart:  c.Query("date_start"),
		DateEnd:    c.Query("date_end"),
		TargetType: c.Query("target_type"),
		Keyword:    c.Query("keyword"),
		Page:       1,
		PageSize:   100000, // export all matching
	}
	if tt := c.Query("threat_types"); tt != "" {
		p.ThreatTypes = splitCSV(tt)
	}
	if tl := c.Query("threat_levels"); tl != "" {
		p.ThreatLevels = splitCSV(tl)
	}

	items, _, err := h.Repo.GetAlerts(p)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	filename := fmt.Sprintf("alerts_export_%s.csv", time.Now().Format("20060102_150405"))
	c.Header("Content-Type", "text/csv")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%s", filename))

	w := csv.NewWriter(c.Writer)
	// Header row
	w.Write([]string{
		"设备ID", "源IP", "外联目标", "端口", "威胁类型", "威胁等级",
		"标准APT组织", "APT组织", "APT分级", "厂商", "告警次数",
		"首次告警时间", "最近告警时间",
	})
	for _, item := range items {
		w.Write([]string{
			fmt.Sprint(item["device_id"]),
			fmt.Sprint(item["source_ip"]),
			fmt.Sprint(item["target"]),
			fmt.Sprint(item["port"]),
			fmt.Sprint(item["threat_type"]),
			fmt.Sprint(item["threat_level"]),
			fmt.Sprint(item["std_apt_org"]),
			fmt.Sprint(item["apt_org"]),
			fmt.Sprint(item["apt_org_tier"]),
			fmt.Sprint(item["vendors"]),
			fmt.Sprint(item["alert_count"]),
			fmt.Sprint(item["first_alert_time"]),
			fmt.Sprint(item["last_alert_time"]),
		})
	}
	w.Flush()
}

// AnnotateAlert PATCH /api/alerts/{id}/annotation
func (h *AlertHandler) AnnotateAlert(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))

	var req struct {
		AnalysisStatus string `json:"analysis_status"`
		IsFocused      *bool  `json:"is_focused"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	updates := []string{}
	args := []interface{}{}
	argIdx := 1

	if req.AnalysisStatus != "" {
		updates = append(updates, fmt.Sprintf("analysis_status = $%d", argIdx))
		args = append(args, req.AnalysisStatus)
		argIdx++
	}
	if req.IsFocused != nil {
		focused := 0
		if *req.IsFocused {
			focused = 1
		}
		updates = append(updates, fmt.Sprintf("is_focused = $%d", argIdx))
		args = append(args, focused)
		argIdx++
	}

	if len(updates) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "No fields to update"})
		return
	}

	args = append(args, id)
	sql := fmt.Sprintf("UPDATE alerts SET %s WHERE id = $%d", strings.Join(updates, ", "), argIdx)
	result, err := h.Repo.DB.Exec(sql, args...)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Database error: " + err.Error()})
		return
	}

	affected, _ := result.RowsAffected()
	if affected == 0 {
		c.JSON(http.StatusNotFound, gin.H{"error": "Alert not found"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"ok": true})
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
