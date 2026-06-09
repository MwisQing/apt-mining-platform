package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/repository"
)

type DeviceHandler struct {
	Repo *repository.DeviceRepo
}

func NewDeviceHandler(repo *repository.DeviceRepo) *DeviceHandler {
	return &DeviceHandler{Repo: repo}
}

func (h *DeviceHandler) ListDevices(c *gin.Context) {
	keyword := c.Query("keyword")
	tags := c.Query("tags")
	page := parseInt(c.Query("page"), 1)
	pageSize := parseInt(c.Query("page_size"), 50)

	items, total, err := h.Repo.Query(keyword, tags, page, pageSize)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"items":     items,
		"total":     total,
		"page":      page,
		"page_size": pageSize,
	})
}

// AddDeviceTags POST /api/devices/:id/tags
func (h *DeviceHandler) AddDeviceTags(c *gin.Context) {
	deviceID := c.Param("id")
	var req struct {
		Tags []string `json:"tags"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.AddDeviceTags(deviceID, req.Tags); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// RemoveDeviceTag DELETE /api/devices/:id/tags/:tag_name
func (h *DeviceHandler) RemoveDeviceTag(c *gin.Context) {
	deviceID := c.Param("id")
	tagName := c.Param("tag_name")
	if err := h.Repo.RemoveDeviceTag(deviceID, tagName); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}
