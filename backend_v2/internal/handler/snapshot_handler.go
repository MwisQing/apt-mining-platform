package handler

import (
	"database/sql"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
)

type SnapshotHandler struct {
	DB *sql.DB
}

func NewSnapshotHandler(db *sql.DB) *SnapshotHandler {
	return &SnapshotHandler{DB: db}
}

// GetStatus GET /api/snapshots/status
// Go backend uses real-time queries (no snapshot table), always returns "ready".
func (h *SnapshotHandler) GetStatus(c *gin.Context) {
	var rowCount int64
	// pg_class.reltuples 是 autovacuum 维护的估算值，零 DB 开销。
	// reltuples < 0 表示从未统计过，回退到 0。
	h.DB.QueryRow("SELECT CASE WHEN reltuples < 0 THEN 0 ELSE reltuples END::bigint FROM pg_class WHERE relname = 'alerts'").Scan(&rowCount)

	c.JSON(http.StatusOK, gin.H{
		"status":         "ready",
		"last_built_at":  time.Now().Format("2006-01-02 15:04:05"),
		"last_row_count": rowCount,
		"last_error":     nil,
	})
}

// Rebuild POST /api/snapshots/rebuild
// Go backend performs real-time candidate queries; no snapshot rebuild needed.
// This endpoint exists for frontend API compatibility and returns immediate success.
func (h *SnapshotHandler) Rebuild(c *gin.Context) {
	var rowCount int64
	// pg_class.reltuples 是 autovacuum 维护的估算值，零 DB 开销。
	// reltuples < 0 表示从未统计过，回退到 0。
	h.DB.QueryRow("SELECT CASE WHEN reltuples < 0 THEN 0 ELSE reltuples END::bigint FROM pg_class WHERE relname = 'alerts'").Scan(&rowCount)

	c.JSON(http.StatusOK, gin.H{
		"status":         "ready",
		"message":        "Go backend uses real-time queries; snapshot rebuild is a no-op",
		"last_built_at":  time.Now().Format("2006-01-02 15:04:05"),
		"last_row_count": rowCount,
	})
}
