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
