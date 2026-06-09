package handler

import (
	"crypto/sha256"
	"encoding/csv"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/service"
)

type ImportHandler struct {
	Service   *service.ImportService
	UploadDir string
}

func NewImportHandler(svc *service.ImportService, uploadDir string) *ImportHandler {
	return &ImportHandler{Service: svc, UploadDir: uploadDir}
}

// UploadExcel POST /api/imports
func (h *ImportHandler) UploadExcel(c *gin.Context) {
	// Ensure upload directory exists
	if err := os.MkdirAll(h.UploadDir, 0755); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("create upload dir: %v", err)})
		return
	}

	// Increase multipart memory limit for large Excel files (up to 500MB)
	c.Request.ParseMultipartForm(500 << 20)

	file, err := c.FormFile("files")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no file uploaded"})
		return
	}

	filename := filepath.Base(file.Filename)
	destPath := filepath.Join(h.UploadDir, filename)
	if err := c.SaveUploadedFile(file, destPath); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("save file: %v", err)})
		return
	}

	// Compute SHA256 hash for deduplication
	fileHash, err := computeFileHash(destPath)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("hash file: %v", err)})
		return
	}

	job, err := h.Service.CreateImport(filename, fileHash)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": fmt.Sprintf("create import: %v", err)})
		return
	}

	// 重复文件：删除刚保存的临时文件
	if dup, _ := job["duplicate"].(bool); dup {
		os.Remove(destPath)
	}

	c.JSON(http.StatusOK, job)
}

func computeFileHash(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return fmt.Sprintf("%x", h.Sum(nil)), nil
}

// ListImports GET /api/imports
func (h *ImportHandler) ListImports(c *gin.Context) {
	imports, err := h.Service.ListImports()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, imports)
}

// GetImport GET /api/imports/{id}
func (h *ImportHandler) GetImport(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	job, err := h.Service.GetImport(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "import not found"})
		return
	}
	c.JSON(http.StatusOK, job)
}

// GetImportSheets GET /api/imports/{id}/sheets
func (h *ImportHandler) GetImportSheets(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	sheets, err := h.Service.GetImportSheets(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, sheets)
}

// DeleteImport DELETE /api/imports/{id}
func (h *ImportHandler) DeleteImport(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	if err := h.Service.DeleteImport(id); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// GetImportRows GET /api/imports/{id}/rows
func (h *ImportHandler) GetImportRows(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	sheetID := parseInt(c.Query("sheet_id"), 0)
	// Frontend sends status_group=issues|skipped; backend maps to internal status values.
	statusGroup := c.Query("status_group")
	switch statusGroup {
	case "issues":
		statusGroup = "failed"
	case "skipped":
		statusGroup = "skipped_duplicate"
	}
	page := parseInt(c.Query("page"), 1)
	pageSize := parseInt(c.Query("page_size"), 50)

	rows, total := h.Service.GetImportRows(id, sheetID, statusGroup, page, pageSize)
	c.JSON(http.StatusOK, gin.H{
		"items":     rows,
		"total":     total,
		"page":      page,
		"page_size": pageSize,
	})
}

// GetImportFailures GET /api/imports/{id}/failures.csv
func (h *ImportHandler) GetImportFailures(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	failureType := c.DefaultQuery("type", "failures")

	filename, data, err := h.Service.GetImportFailures(id, failureType)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.Header("Content-Type", "text/csv")
	c.Header("Content-Disposition", fmt.Sprintf("attachment; filename=%s", filename))

	w := csv.NewWriter(c.Writer)
	w.WriteAll(data)
}

// DeleteAllImports DELETE /api/imports/all
func (h *ImportHandler) DeleteAllImports(c *gin.Context) {
	if err := h.Service.DeleteAllImports(); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// ReprocessQueuedImports POST /api/imports/reprocess-queued
func (h *ImportHandler) ReprocessQueuedImports(c *gin.Context) {
	count, err := h.Service.ReprocessQueuedImports()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"reprocessed": count, "requeued": count})
}

// RepairImportMetadata POST /api/imports/{id}/repair-metadata
func (h *ImportHandler) RepairImportMetadata(c *gin.Context) {
	id, _ := strconv.Atoi(c.Param("id"))
	stats, err := h.Service.RepairImportMetadata(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, stats)
}
