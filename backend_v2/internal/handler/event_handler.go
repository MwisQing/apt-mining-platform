package handler

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/repository"
	"apt-mining-platform/v2/internal/service"
)

type EventHandler struct {
	Repo      *repository.EventRepo
	Extractor *service.IOCExtractor
}

func NewEventHandler(repo *repository.EventRepo, ext *service.IOCExtractor) *EventHandler {
	return &EventHandler{Repo: repo, Extractor: ext}
}

// ListEvents GET /api/events
func (h *EventHandler) ListEvents(c *gin.Context) {
	events, err := h.Repo.ListEvents(c.Query("status"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if events == nil {
		events = []repository.Event{}
	}
	c.JSON(http.StatusOK, events)
}

// GetEvent GET /api/events/{id}
func (h *EventHandler) GetEvent(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	detail, err := h.Repo.GetEvent(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "event not found"})
		return
	}
	c.JSON(http.StatusOK, detail)
}

// CreateEvent POST /api/events
func (h *EventHandler) CreateEvent(c *gin.Context) {
	var req struct {
		EventName string             `json:"event_name"`
		Color     string             `json:"color"`
		Note      string             `json:"note"`
		Devices   []string           `json:"devices"`
		IOCs      []repository.IOC   `json:"iocs"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var iocItems []repository.IOC
	for _, ioc := range req.IOCs {
		iocItems = append(iocItems, repository.IOC{
			Target: strings.TrimSpace(ioc.Target),
			Port:   strings.TrimSpace(ioc.Port),
		})
	}

	id, err := h.Repo.CreateEventTx(req.EventName, req.Color, req.Note, req.Devices, iocItems)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{"id": id})
}

// UpdateEvent PATCH /api/events/{id}
func (h *EventHandler) UpdateEvent(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	var req struct {
		EventName string `json:"event_name"`
		Color     string `json:"color"`
		Status    string `json:"status"`
		Note      string `json:"note"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.UpdateEvent(id, req.EventName, req.Color, req.Status, req.Note); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// DeleteEvent DELETE /api/events/{id}
func (h *EventHandler) DeleteEvent(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	if err := h.Repo.DeleteEvent(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// AddFollowup POST /api/events/{id}/followups
func (h *EventHandler) AddFollowup(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	var req struct {
		ActionType string `json:"action_type"`
		Note       string `json:"note"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.AddFollowup(id, req.ActionType, req.Note); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// AddDevices POST /api/events/{id}/devices
func (h *EventHandler) AddDevices(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	var req struct {
		Devices []string `json:"devices"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.AddDevices(id, req.Devices); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// AddIOCs POST /api/events/{id}/iocs
func (h *EventHandler) AddIOCs(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	var req struct {
		IOCs []repository.IOC `json:"iocs"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	var iocItems []repository.IOC
	for _, ioc := range req.IOCs {
		iocItems = append(iocItems, repository.IOC{
			Target: strings.TrimSpace(ioc.Target),
			Port:   strings.TrimSpace(ioc.Port),
		})
	}
	if err := h.Repo.AddIOCs(id, iocItems); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// RemoveDevice DELETE /api/events/{id}/devices/{device_id}
func (h *EventHandler) RemoveDevice(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	deviceID := c.Param("device_id")
	if err := h.Repo.RemoveDevice(id, deviceID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// RemoveIoc DELETE /api/events/{id}/iocs
func (h *EventHandler) RemoveIoc(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	target := c.Query("target")
	port := c.Query("port")
	if err := h.Repo.RemoveIOCs(id, target, port); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// ExtractIOCs POST /api/events/extract-iocs
func (h *EventHandler) ExtractIOCs(c *gin.Context) {
	var req struct {
		Text string `json:"text"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	iocs := h.Extractor.ExtractIOCs(req.Text)
	if iocs == nil {
		iocs = []service.IOCItem{}
	}

	// Separate devices (type=="device") from other IOCs for frontend compatibility
	var devices []string
	var nonDevices []service.IOCItem
	for _, item := range iocs {
		if item.Type == "device" {
			devices = append(devices, item.Value)
		} else {
			nonDevices = append(nonDevices, item)
		}
	}
	if nonDevices == nil {
		nonDevices = []service.IOCItem{}
	}
	if devices == nil {
		devices = []string{}
	}

	c.JSON(http.StatusOK, gin.H{"iocs": nonDevices, "devices": devices})
}
