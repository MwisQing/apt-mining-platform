package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/config"
)

type ConfigHandler struct {
	Cfg *config.Config
}

func NewConfigHandler(cfg *config.Config) *ConfigHandler { return &ConfigHandler{Cfg: cfg} }

func (h *ConfigHandler) GetConfig(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"trace_ttl_days":      h.Cfg.Rules.TraceTTLDays,
		"default_hide_traced": h.Cfg.Rules.DefaultHideTraced,
		"default_hide_closed": h.Cfg.Rules.DefaultHideClosedEvts,
		"badges":              h.Cfg.Badges.Enabled,
		"dict_apt":            h.Cfg.Paths.DictAPT,
		"dict_crime":          h.Cfg.Paths.DictCrime,
		"dict_noise":          h.Cfg.Paths.DictNoise,
	})
}

func (h *ConfigHandler) SaveConfig(c *gin.Context) {
	var req struct {
		TraceTTLDays      int      `json:"trace_ttl_days"`
		DefaultHideTraced *bool    `json:"default_hide_traced"`
		DefaultHideClosed *bool    `json:"default_hide_closed"`
		Badges            []string `json:"badges"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	if req.TraceTTLDays > 0 {
		h.Cfg.Rules.TraceTTLDays = req.TraceTTLDays
	}
	if req.DefaultHideTraced != nil {
		h.Cfg.Rules.DefaultHideTraced = *req.DefaultHideTraced
	}
	if req.DefaultHideClosed != nil {
		h.Cfg.Rules.DefaultHideClosedEvts = *req.DefaultHideClosed
	}
	if req.Badges != nil {
		h.Cfg.Badges.Enabled = req.Badges
	}

	if err := config.Save(); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to persist config: " + err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *ConfigHandler) ReloadDicts(c *gin.Context) {
	// Re-read dictionary YAML files into memory
	config.ReloadDicts()
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *ConfigHandler) GetDicts(c *gin.Context) {
	dicts := map[string]map[string]string{
		"apt_org": config.GetDict(h.Cfg.Paths.DictAPT),
		"crime":   config.GetDict(h.Cfg.Paths.DictCrime),
		"noise":   config.GetDict(h.Cfg.Paths.DictNoise),
	}
	c.JSON(http.StatusOK, dicts)
}
