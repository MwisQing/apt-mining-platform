package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/repository"
)

type AuditHandler struct {
	Repo *repository.AuditRepo
}

func NewAuditHandler(repo *repository.AuditRepo) *AuditHandler {
	return &AuditHandler{Repo: repo}
}

// GetAuditLogs GET /api/audit-log
func (h *AuditHandler) GetAuditLogs(c *gin.Context) {
	p := &repository.AuditQueryParams{
		DateStart: c.Query("date_start"),
		DateEnd:   c.Query("date_end"),
		Action:    c.Query("action_type"),
		Keyword:   c.Query("keyword"),
		Page:      parseInt(c.Query("page"), 1),
		PageSize:  parseInt(c.Query("page_size"), 50),
	}

	items, total, err := h.Repo.QueryLogs(p)
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

// GetAuditActions GET /api/audit-log/actions — 操作类型选项
func (h *AuditHandler) GetAuditActions(c *gin.Context) {
	actions, err := h.Repo.GetActionOptions()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"actions": actions})
}
