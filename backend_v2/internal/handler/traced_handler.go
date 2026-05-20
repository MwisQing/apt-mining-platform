package handler

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/xuri/excelize/v2"

	"apt-mining-platform/v2/internal/repository"
)

type TracedHandler struct {
	Repo *repository.TracedRepo
}

func NewTracedHandler(repo *repository.TracedRepo) *TracedHandler {
	return &TracedHandler{Repo: repo}
}

func (h *TracedHandler) ListTraced(c *gin.Context) {
	items, err := h.Repo.List(c.Query("keyword"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, items)
}

// AddTraced POST /api/traced — accepts single object or array
func (h *TracedHandler) AddTraced(c *gin.Context) {
	// Try array first
	var arr []struct {
		Target string `json:"target"`
		Port   string `json:"port"`
		Note   string `json:"note"`
	}
	if err := c.ShouldBindJSON(&arr); err == nil && len(arr) > 0 {
		items := make([]repository.TracedItem, len(arr))
		for i, item := range arr {
			items[i] = repository.TracedItem{Target: item.Target, Port: item.Port, Note: item.Note}
		}
		count, err := h.Repo.BatchCreate(items)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusCreated, gin.H{"imported": count})
		return
	}

	// Fall back to single object
	var single struct {
		Target string `json:"target"`
		Port   string `json:"port"`
		Note   string `json:"note"`
	}
	if err := c.ShouldBindJSON(&single); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.Create(single.Target, single.Port, single.Note); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"ok": true})
}

func (h *TracedHandler) UpdateTraced(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	var req struct {
		Target string `json:"target"`
		Port   string `json:"port"`
		Note   string `json:"note"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.Update(id, req.Target, req.Port, req.Note); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *TracedHandler) DeleteTraced(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	if err := h.Repo.Delete(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// ImportTracedExcel POST /api/traced/import
func (h *TracedHandler) ImportTracedExcel(c *gin.Context) {
	file, err := c.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no file uploaded"})
		return
	}

	f, err := file.Open()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "cannot open file"})
		return
	}
	defer f.Close()

	xlsx, err := excelize.OpenReader(f)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "invalid excel file: " + err.Error()})
		return
	}
	defer xlsx.Close()

	sheets := xlsx.GetSheetList()
	if len(sheets) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "excel has no sheets"})
		return
	}

	rows, err := xlsx.GetRows(sheets[0])
	if err != nil || len(rows) < 2 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "excel has no data rows"})
		return
	}

	// Build header map
	headers := rows[0]
	headerMap := make(map[string]int)
	for i, h := range headers {
		headerMap[strings.TrimSpace(h)] = i
	}

	get := func(row []string, name string) string {
		if idx, ok := headerMap[name]; ok && idx < len(row) {
			return strings.TrimSpace(row[idx])
		}
		return ""
	}

	imported := 0
	for i := 1; i < len(rows); i++ {
		row := rows[i]
		target := get(row, "target")
		if target == "" {
			target = get(row, "IOC")
		}
		if target == "" {
			continue
		}
		port := get(row, "port")
		note := get(row, "note")
		if err := h.Repo.Create(target, port, note); err == nil {
			imported++
		}
	}

	c.JSON(http.StatusOK, gin.H{"imported": imported})
}
