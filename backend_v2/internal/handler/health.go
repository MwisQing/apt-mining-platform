package handler

import (
	"database/sql"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/config"
)

type HealthHandler struct {
	DB *sql.DB
}

func NewHealthHandler(db *sql.DB) *HealthHandler {
	return &HealthHandler{DB: db}
}

// Health GET /api/health
func (h *HealthHandler) Health(c *gin.Context) {
	if err := h.DB.Ping(); err != nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"status":  "error",
			"message": "database connection failed",
			"error":   err.Error(),
		})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status":  "ok",
		"message": "APT Mining Workbench v2.0",
	})
}

type VersionHandler struct{}

func NewVersionHandler() *VersionHandler {
	return &VersionHandler{}
}

// Persistence GET /api/persistence — cross-day persistent connections
func (h *HealthHandler) Persistence(c *gin.Context) {
	minDays := parseInt(c.DefaultQuery("min_days", "2"), 2)
	since := c.Query("since")
	limit := parseInt(c.DefaultQuery("limit", "100"), 100)
	if limit < 1 {
		limit = 100
	}
	if limit > 5000 {
		limit = 5000
	}

	query := `
		SELECT source_ip, target,
		       COUNT(DISTINCT DATE(first_alert_time)) AS days,
		       to_char(MIN(first_alert_time), 'YYYY-MM-DD HH24:MI:SS') AS first_seen,
		       to_char(MAX(last_alert_time), 'YYYY-MM-DD HH24:MI:SS') AS last_seen,
		       SUM(alert_count) AS total_alerts
		FROM alerts
	`
	args := []interface{}{}
	argIdx := 1
	if since != "" {
		query += " WHERE first_alert_time >= $1"
		args = append(args, since+" 00:00:00")
		argIdx++
	}
	query += fmt.Sprintf(" GROUP BY source_ip, target HAVING COUNT(DISTINCT DATE(first_alert_time)) >= $%d", argIdx)
	args = append(args, minDays)
	argIdx++
	query += fmt.Sprintf(" ORDER BY days DESC, total_alerts DESC LIMIT $%d", argIdx)
	args = append(args, limit)

	rows, err := h.DB.Query(query, args...)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	defer rows.Close()

	type PersistenceItem struct {
		SourceIP    string `json:"source_ip"`
		Target      string `json:"target"`
		Days        int    `json:"days"`
		FirstSeen   string `json:"first_seen"`
		LastSeen    string `json:"last_seen"`
		TotalAlerts int64  `json:"total_alerts"`
	}

	var items []PersistenceItem
	for rows.Next() {
		var item PersistenceItem
		rows.Scan(&item.SourceIP, &item.Target, &item.Days, &item.FirstSeen, &item.LastSeen, &item.TotalAlerts)
		items = append(items, item)
	}
	if items == nil {
		items = []PersistenceItem{}
	}
	c.JSON(http.StatusOK, items)
}

// Version GET /api/version
func (h *VersionHandler) Version(c *gin.Context) {
	version := "unknown"
	// 基于可执行文件所在目录查找 VERSION 文件
	baseDir := config.BaseDir()
	versionPath := filepath.Join(baseDir, "VERSION")
	if data, err := os.ReadFile(versionPath); err == nil {
		version = strings.TrimSpace(string(data))
	}

	c.JSON(http.StatusOK, gin.H{
		"version":    version,
		"engine":     "go",
		"repository": "https://github.com/user/apt-mining-platform",
	})
}
