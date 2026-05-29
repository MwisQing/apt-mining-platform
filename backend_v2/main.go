package main

import (
	"fmt"
	"log"
	"net/http"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/config"
	"apt-mining-platform/v2/internal/db"
	"apt-mining-platform/v2/internal/handler"
	"apt-mining-platform/v2/internal/repository"
	"apt-mining-platform/v2/internal/service"
)

func main() {
	if err := config.Init("config/config.yaml"); err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}
	cfg := config.Get()
	log.Printf("Config loaded: host=%s port=%d", cfg.Server.Host, cfg.Server.Port)

	database := db.MustConnect()
	defer database.Close()
	log.Println("Database connected")

	migrationsDir := config.ResolvePath("migrations")
	if err := db.RunMigrations(database, migrationsDir); err != nil {
		log.Printf("Migration warning: %v", err)
	}
	log.Println("Migrations complete")

	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()

	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	})

	r.Static("/assets", config.ResolvePath("static/assets"))
	r.StaticFile("/columns.json", config.ResolvePath("static/columns.json"))
	r.NoRoute(func(c *gin.Context) {
		c.File(config.ResolvePath("static/index.html"))
	})

	// Repos
	candidateRepo := repository.NewCandidateRepo(database)
	eventRepo := repository.NewEventRepo(database)
	tagRepo := repository.NewTagRepo(database)
	tracedRepo := repository.NewTracedRepo(database)
	deviceRepo := repository.NewDeviceRepo(database)
	auditRepo := repository.NewAuditRepo(database)

	// Services
	candidateSvc := service.NewCandidateService(candidateRepo, cfg)
	importSvc := service.NewImportService(database, config.ResolvePath("uploads"))
	iocExt := service.NewIOCExtractor()

	// Handlers
	healthHandler := handler.NewHealthHandler(database)
	versionHandler := handler.NewVersionHandler()
	candidateHandler := handler.NewCandidateHandler(candidateSvc)
	alertHandler := handler.NewAlertHandler(candidateRepo)
	importHandler := handler.NewImportHandler(importSvc, config.ResolvePath("uploads"))
	eventHandler := handler.NewEventHandler(eventRepo, iocExt)
	tagHandler := handler.NewTagHandler(tagRepo)
	tracedHandler := handler.NewTracedHandler(tracedRepo)
	deviceHandler := handler.NewDeviceHandler(deviceRepo)
	snapshotHandler := handler.NewSnapshotHandler(database)
	configHandler := handler.NewConfigHandler(cfg)
	auditHandler := handler.NewAuditHandler(auditRepo)

	api := r.Group("/api")
	{
		api.GET("/health", healthHandler.Health)
		api.GET("/version", versionHandler.Version)

		api.GET("/alert-candidates", candidateHandler.QueryCandidates)
		api.GET("/alerts", alertHandler.ListAlerts)
		api.GET("/alerts/options", alertHandler.GetFilterOptions)
		api.POST("/alerts/export", alertHandler.ExportAlerts)
		api.PATCH("/alerts/:id/annotation", alertHandler.AnnotateAlert)

		api.POST("/imports", importHandler.UploadExcel)
		api.GET("/imports", importHandler.ListImports)
		api.GET("/imports/:id", importHandler.GetImport)
		api.GET("/imports/:id/sheets", importHandler.GetImportSheets)
		api.GET("/imports/:id/rows", importHandler.GetImportRows)
		api.GET("/imports/:id/failures.csv", importHandler.GetImportFailures)
		api.DELETE("/imports/:id", importHandler.DeleteImport)
		api.DELETE("/imports/all", importHandler.DeleteAllImports)
		api.POST("/imports/reprocess-queued", importHandler.ReprocessQueuedImports)
		api.POST("/imports/:id/repair-metadata", importHandler.RepairImportMetadata)

		api.GET("/events", eventHandler.ListEvents)
		api.GET("/events/:id", eventHandler.GetEvent)
		api.POST("/events", eventHandler.CreateEvent)
		api.PATCH("/events/:id", eventHandler.UpdateEvent)
		api.DELETE("/events/:id", eventHandler.DeleteEvent)
		api.POST("/events/:id/followups", eventHandler.AddFollowup)
		api.POST("/events/:id/devices", eventHandler.AddDevices)
		api.POST("/events/:id/iocs", eventHandler.AddIOCs)
		api.DELETE("/events/:id/devices/:device_id", eventHandler.RemoveDevice)
		api.DELETE("/events/:id/iocs", eventHandler.RemoveIoc)
		api.POST("/events/extract-iocs", eventHandler.ExtractIOCs)

		api.GET("/tags", tagHandler.ListTags)
		api.GET("/tags/batches", tagHandler.ListBatches)
		api.GET("/tags/batches/:id", tagHandler.GetBatchDetail)
		api.POST("/tags/batches", tagHandler.CreateBatch)
		api.DELETE("/tags/batches/:id", tagHandler.DeleteBatch)
		api.POST("/tags/batches/:id/restore", tagHandler.RestoreBatch)
		api.DELETE("/tags/batches/:id/devices", tagHandler.RemoveBatchDevices)
		api.GET("/tags/devices/:device_id/tags", tagHandler.GetDeviceTags)
		api.POST("/tags/devices/tags", tagHandler.AddDeviceTag)
		api.POST("/tags/devices/batch", tagHandler.BatchTagDevices)
		api.PATCH("/tags/tags/:id", tagHandler.UpdateTagColor)
		api.POST("/tags/batches/import-text-files", tagHandler.ImportTextFiles)
		api.DELETE("/tags/devices/batch", tagHandler.BatchRemoveDeviceTags)
		api.DELETE("/tags/devices/:device_id/tags/:tag_id", tagHandler.RemoveDeviceTag)

		api.GET("/traced", tracedHandler.ListTraced)
		api.POST("/traced", tracedHandler.AddTraced)
		api.PATCH("/traced/:id", tracedHandler.UpdateTraced)
		api.DELETE("/traced/:id", tracedHandler.DeleteTraced)
		api.POST("/traced/import", tracedHandler.ImportTracedExcel)

		api.GET("/devices", deviceHandler.ListDevices)
		api.POST("/devices/:id/tags", deviceHandler.AddDeviceTags)
		api.DELETE("/devices/:id/tags/:tag_name", deviceHandler.RemoveDeviceTag)

		api.GET("/audit-log", auditHandler.GetAuditLogs)
		api.GET("/audit-log/actions", auditHandler.GetAuditActions)

		api.GET("/config", configHandler.GetConfig)
		api.POST("/config", configHandler.SaveConfig)
		api.POST("/config/reload", configHandler.ReloadDicts)
		api.GET("/config/dicts", configHandler.GetDicts)

		api.GET("/snapshots/status", snapshotHandler.GetStatus)
		api.POST("/snapshots/rebuild", snapshotHandler.Rebuild)
		api.GET("/persistence", healthHandler.Persistence)
	}

	addr := fmt.Sprintf("%s:%d", cfg.Server.Host, cfg.Server.Port)
	log.Printf("Server starting on %s", addr)
	if err := r.Run(addr); err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
}
