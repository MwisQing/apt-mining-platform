package handler

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/repository"
)

type TagHandler struct {
	Repo *repository.TagRepo
}

func NewTagHandler(repo *repository.TagRepo) *TagHandler { return &TagHandler{Repo: repo} }

func (h *TagHandler) ListTags(c *gin.Context) {
	tags, err := h.Repo.ListTags()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if tags == nil {
		tags = []repository.Tag{}
	}
	c.JSON(http.StatusOK, tags)
}

func (h *TagHandler) ListBatches(c *gin.Context) {
	batches, err := h.Repo.ListBatches()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if batches == nil {
		batches = []repository.TagBatch{}
	}
	c.JSON(http.StatusOK, batches)
}

func (h *TagHandler) CreateBatch(c *gin.Context) {
	var req struct {
		BatchName string   `json:"batch_name"`
		TagName   string   `json:"tag_name"`
		Color     string   `json:"color"`
		Devices   []string `json:"devices"`
		Note      string   `json:"note"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	batchID, err := h.Repo.CreateBatch(req.BatchName, req.TagName, req.Color, req.Devices, req.Note)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"id": batchID})
}

func (h *TagHandler) DeleteBatch(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	if err := h.Repo.DeleteBatch(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *TagHandler) RestoreBatch(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	count, err := h.Repo.RestoreBatch(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "restored_count": count})
}

func (h *TagHandler) GetDeviceTags(c *gin.Context) {
	tags, err := h.Repo.GetDeviceTags(c.Param("device_id"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, tags)
}

func (h *TagHandler) AddDeviceTag(c *gin.Context) {
	var req struct {
		DeviceID string `json:"device_id"`
		TagName  string `json:"tag_name"`
		Color    string `json:"color"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.AddDeviceTag(req.DeviceID, req.TagName, req.Color); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *TagHandler) UpdateTagColor(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	var req struct {
		Color string `json:"color"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.UpdateTagColor(id, req.Color); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *TagHandler) BatchTagDevices(c *gin.Context) {
	var req struct {
		Devices []string `json:"devices"`
		TagName string   `json:"tag_name"`
		Color   string   `json:"color"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	count, err := h.Repo.BatchTagDevices(req.Devices, req.TagName, req.Color)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"imported": count})
}

func (h *TagHandler) ImportTextFiles(c *gin.Context) {
	form, err := c.MultipartForm()
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid multipart form"})
		return
	}
	files := form.File["files"]
	if len(files) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no files uploaded"})
		return
	}

	totalImported := 0
	for _, fileHeader := range files {
		file, err := fileHeader.Open()
		if err != nil {
			continue
		}
		buf := make([]byte, fileHeader.Size)
		file.Read(buf)
		file.Close()

		var devices []string
		for _, line := range strings.Split(string(buf), "\n") {
			line = strings.TrimSpace(line)
			if line != "" {
				devices = append(devices, line)
			}
		}
		if len(devices) == 0 {
			continue
		}

		// Apply preset matching based on filename, matching 3.x Python behavior
		batchName := strings.TrimSuffix(fileHeader.Filename, ".txt")
		tagName, tagColor := matchTagPreset(fileHeader.Filename)
		if tagName == "" {
			tagName = batchName
			tagColor = "#409EFF"
		}

		batchID, err := h.Repo.CreateBatch(batchName, tagName, tagColor, devices,
			"TXT批量导入: "+fileHeader.Filename)
		if err == nil {
			totalImported += len(devices)
			_ = batchID
		}
	}

	c.JSON(http.StatusOK, gin.H{"imported": totalImported})
}

// txtTagPreset defines an automatic tag preset based on filename matching.
type txtTagPreset struct {
	matchTokens []string
	tagName     string
	tagColor    string
}

// txtTagPresets matches the 3.x Python TXT_TAG_IMPORT_PRESETS exactly.
var txtTagPresets = []txtTagPreset{
	{matchTokens: []string{"01.", "排查成功", "查实成功"}, tagName: "排查成功", tagColor: "#67C23A"},
	{matchTokens: []string{"02.", "重点设备"}, tagName: "重点设备", tagColor: "#F56C6C"},
	{matchTokens: []string{"03.", "不好查", "不好排查"}, tagName: "不好查", tagColor: "#909399"},
}

// matchTagPreset checks if a filename matches any preset and returns the preset tag name and color.
func matchTagPreset(filename string) (string, string) {
	fnameLower := strings.ToLower(filename)
	for _, preset := range txtTagPresets {
		for _, token := range preset.matchTokens {
			if strings.Contains(fnameLower, strings.ToLower(token)) {
				return preset.tagName, preset.tagColor
			}
		}
	}
	return "", ""
}

// GetBatchDetail GET /api/tags/batches/{id}
func (h *TagHandler) GetBatchDetail(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	batch, err := h.Repo.GetBatchDetail(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "batch not found"})
		return
	}
	c.JSON(http.StatusOK, batch)
}

// RemoveBatchDevices DELETE /api/tags/batches/{id}/devices
func (h *TagHandler) RemoveBatchDevices(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	var req struct {
		Devices []string `json:"devices"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	count, err := h.Repo.RemoveBatchDevices(id, req.Devices)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "removed_count": count})
}

// BatchRemoveDeviceTags DELETE /api/tags/devices/batch
// Accepts either: [{device_id, tag_id}, ...]  OR  {devices:[], tag_id:int}
func (h *TagHandler) BatchRemoveDeviceTags(c *gin.Context) {
	// Try the {devices, tag_id} format first (used by Settings.vue bulk remove)
	var single struct {
		Devices []string `json:"devices"`
		TagID   int      `json:"tag_id"`
	}
	if err := c.ShouldBindJSON(&single); err == nil && len(single.Devices) > 0 && single.TagID > 0 {
		count, err := h.Repo.BatchRemoveDeviceTagsByTagID(single.TagID, single.Devices)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, gin.H{"ok": true, "removed_count": count})
		return
	}

	// Fall back to the [{device_id, tag_id}, ...] format
	c.Request.Body.Read(nil) // Best-effort reset (not critical for this fallback path)
	var reqs []struct {
		DeviceID string `json:"device_id"`
		TagID    int    `json:"tag_id"`
	}
	if err := c.ShouldBindJSON(&reqs); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Expected {devices:[], tag_id:int}"})
		return
	}
	if err := h.Repo.BatchRemoveDeviceTags(reqs); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "removed_count": len(reqs)})
}

func (h *TagHandler) RemoveDeviceTag(c *gin.Context) {
	deviceID := c.Param("device_id")
	tagID, _ := strconv.Atoi(c.Param("tag_id"))
	if err := h.Repo.RemoveDeviceTag(deviceID, tagID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}
