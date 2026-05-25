package service

import (
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/xuri/excelize/v2"
)

// ImportService Excel 导入服务
type ImportService struct {
	DB        *sql.DB
	UploadDir string
	queue     chan int
	queuePos  int
	queueMu   sync.Mutex
}

func NewImportService(db *sql.DB, uploadDir string) *ImportService {
	svc := &ImportService{
		DB:        db,
		UploadDir: uploadDir,
		queue:     make(chan int, 100),
	}
	// 启动队列 worker
	go svc.queueWorker()
	return svc
}

// queueWorker 队列消费者 — 串行处理导入任务，避免并发写锁冲突
func (s *ImportService) queueWorker() {
	for id := range s.queue {
		// 从 DB 获取文件名
		var filename string
		if err := s.DB.QueryRow("SELECT source_file FROM imports WHERE id = $1", id).Scan(&filename); err != nil {
			continue
		}
		// 更新状态为 processing
		s.DB.Exec("UPDATE imports SET status = 'processing' WHERE id = $1", id)
		s.processImport(id, filename)
	}
}

// CreateImport 创建导入任务，入队等待处理。支持文件 Hash 去重。
func (s *ImportService) CreateImport(filename string, fileHash string) (map[string]interface{}, error) {
	// 检查是否已有相同 Hash 的导入记录
	var existID int
	var existFile, existStatus string
	err := s.DB.QueryRow(
		"SELECT id, source_file, status FROM imports WHERE file_hash = $1 AND status != 'failed'",
		fileHash,
	).Scan(&existID, &existFile, &existStatus)
	if err == nil {
		// 已存在相同文件的导入记录，直接返回
		return map[string]interface{}{
			"id":          existID,
			"source_file": existFile,
			"status":      existStatus,
			"duplicate":   true,
		}, nil
	}

	var id int
	err = s.DB.QueryRow(
		"INSERT INTO imports (source_file, imported_at, status, file_hash) VALUES ($1, $2, $3, $4) RETURNING id",
		filename, time.Now(), "queued", fileHash,
	).Scan(&id)
	if err != nil {
		return nil, fmt.Errorf("create import: %w", err)
	}

	s.queueMu.Lock()
	s.queuePos++
	qp := s.queuePos
	s.queueMu.Unlock()

	s.DB.Exec("UPDATE imports SET queue_position = $1 WHERE id = $2", qp, id)

	// 入队（由 queueWorker 消费）
	s.queue <- id

	return map[string]interface{}{
		"id":          id,
		"source_file": filename,
		"status":      "queued",
		"queue_position": qp,
	}, nil
}

// processImport 后台处理单个导入（由 queueWorker 调用）
func (s *ImportService) processImport(id int, filename string) {
	filePath := filepath.Join(s.UploadDir, filename)

	// 使用 excelize 流式读取（OpenReader + Rows 迭代器）
	f, err := excelize.OpenFile(filePath)
	if err != nil {
		s.updateImportStatus(id, "failed", 0, 0, 0, 0, 0, fmt.Sprintf("open excel: %v", err))
		return
	}
	defer f.Close()

	sheets := f.GetSheetList()
	if len(sheets) == 0 {
		s.updateImportStatus(id, "failed", 0, 0, 0, 0, 0, "no sheets found")
		return
	}

	totalInserted := 0
	totalSkipped := 0
	totalFailed := 0
	totalRows := 0

	for sheetIdx, sheetName := range sheets {
		// 使用 Rows 迭代器流式读取，避免 GetRows 全量加载到内存
		rows, err := f.Rows(sheetName)
		if err != nil {
			continue
		}

		// 读取表头
		var headers []string
		if rows.Next() {
			row, _ := rows.Columns()
			headers = row
		}
		if len(headers) < 2 {
			rows.Close()
			continue
		}

		headerMap := make(map[string]int)
		for i, h := range headers {
			headerMap[h] = i
		}

		// 创建 Sheet 记录
		var sheetID int
		s.DB.QueryRow(
			"INSERT INTO import_sheets (import_id, sheet_name, sheet_index, header_row, row_count, status, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
			id, sheetName, sheetIdx, 1, 0, "processing", time.Now(),
		).Scan(&sheetID)

		// 批量插入（SELECT WHERE NOT EXISTS 不依赖唯一索引，适用于非 DBA 环境）
		tx, _ := s.DB.Begin()
		stmt, err := tx.Prepare(`
			INSERT INTO alerts (
				device_id, first_alert_time, last_alert_time, source_ip, target,
				target_type, port, threat_type, threat_level, std_apt_org, apt_org,
				apt_org_tier, alert_count, vendors, protocol, intel_tags, dns_resolved_ip,
				down_traffic, up_traffic, asset_type, source_file, imported_at,
				analysis_status, is_focused, import_id, import_sheet_id, excel_row_number,
				sheet_name, content_hash, unique_hash
			)
			SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30
			WHERE NOT EXISTS (SELECT 1 FROM alerts WHERE content_hash = $29)
		`)
		if err != nil {
			tx.Rollback()
			rows.Close()
			s.updateImportStatus(id, "failed", 0, 0, 0, 0, 0, fmt.Sprintf("prepare stmt: %v", err))
			return
		}

		batchCount := 0
		rowNum := 1
		for rows.Next() {
			row, err := rows.Columns()
			if err != nil {
				continue
			}
			rowNum++
			totalRows++

			vals := extractRow(row, headerMap)
			if vals.DeviceID == "" {
				totalFailed++
				continue
			}

			result, err := stmt.Exec(
				vals.DeviceID, vals.FirstAlertTime, vals.LastAlertTime,
				vals.SourceIP, vals.Target, vals.TargetType, vals.Port,
				vals.ThreatType, vals.ThreatLevel, vals.StdAptOrg, vals.AptOrg,
				vals.AptOrgTier, vals.AlertCount, vals.Vendors, vals.Protocol,
				vals.IntelTags, vals.DNSResolvedIP,
				nil, nil,
				vals.AssetType, filename, time.Now(),
				vals.AnalysisStatus, vals.IsFocused, id, sheetID, rowNum, sheetName,
				vals.ContentHash, vals.UniqueHash,
			)
			if err != nil {
				totalFailed++
				rawJSON, _ := json.Marshal(map[string]interface{}{
					"device_id": vals.DeviceID, "source_ip": vals.SourceIP,
					"target": vals.Target, "port": vals.Port, "threat_type": vals.ThreatType,
				})
				s.DB.Exec(
					"INSERT INTO import_rows (import_id, import_sheet_id, excel_row_number, sheet_name, parse_status, parse_error, raw_json) VALUES ($1,$2,$3,$4,$5,$6,$7)",
					id, sheetID, rowNum, sheetName, "failed", err.Error(), string(rawJSON),
				)
				continue
			}
			affected, _ := result.RowsAffected()
			var alertID int64
			if affected > 0 {
				totalInserted++
				batchCount++
				s.DB.QueryRow("SELECT id FROM alerts WHERE content_hash = $1 AND import_id = $2 ORDER BY id DESC LIMIT 1", vals.ContentHash, id).Scan(&alertID)
				rawJSON, _ := json.Marshal(map[string]interface{}{
					"device_id": vals.DeviceID, "source_ip": vals.SourceIP,
					"target": vals.Target, "port": vals.Port, "threat_type": vals.ThreatType,
					"threat_level": vals.ThreatLevel, "apt_org": vals.AptOrg,
					"std_apt_org": vals.StdAptOrg, "alert_count": vals.AlertCount,
				})
				s.DB.Exec(
					"INSERT INTO import_rows (import_id, import_sheet_id, excel_row_number, sheet_name, parse_status, raw_json, alert_id) VALUES ($1,$2,$3,$4,$5,$6,$7)",
					id, sheetID, rowNum, sheetName, "parsed", string(rawJSON), alertID,
				)
			} else {
				totalSkipped++
				rawJSON, _ := json.Marshal(map[string]interface{}{
					"device_id": vals.DeviceID, "source_ip": vals.SourceIP,
					"target": vals.Target, "port": vals.Port, "threat_type": vals.ThreatType,
				})
				s.DB.Exec(
					"INSERT INTO import_rows (import_id, import_sheet_id, excel_row_number, sheet_name, parse_status, raw_json) VALUES ($1,$2,$3,$4,$5,$6)",
					id, sheetID, rowNum, sheetName, "skipped_duplicate", string(rawJSON),
				)
			}

			// 每 500 行 commit 一次
			if batchCount >= 500 {
				tx.Commit()
				s.DB.Exec("UPDATE import_sheets SET parsed_rows = $1, status = 'processing' WHERE id = $2", totalRows, sheetID)
				tx, _ = s.DB.Begin()
				stmt, _ = tx.Prepare(`
					INSERT INTO alerts (
						device_id, first_alert_time, last_alert_time, source_ip, target,
						target_type, port, threat_type, threat_level, std_apt_org, apt_org,
						apt_org_tier, alert_count, vendors, protocol, intel_tags, dns_resolved_ip,
						down_traffic, up_traffic, asset_type, source_file, imported_at,
						analysis_status, is_focused, import_id, import_sheet_id, excel_row_number,
						sheet_name, content_hash, unique_hash
					)
					SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30
					WHERE NOT EXISTS (SELECT 1 FROM alerts WHERE content_hash = $29)
				`)
				batchCount = 0
			}
		}
		rows.Close()
		tx.Commit()
		stmt.Close()

		s.DB.Exec("UPDATE import_sheets SET status = 'completed', parsed_rows = $1, row_count = $2 WHERE id = $3", totalRows, totalRows, sheetID)
	}

	log := fmt.Sprintf("导入完成: 成功 %d, 跳过 %d, 失败 %d", totalInserted, totalSkipped, totalFailed)
	s.updateImportStatus(id, "completed", totalInserted, totalSkipped, totalFailed, totalRows, totalRows, log)
}

type alertRow struct {
	DeviceID, FirstAlertTime, LastAlertTime string
	SourceIP, Target, TargetType, Port      string
	ThreatType, ThreatLevel, StdAptOrg      string
	AptOrg, AptOrgTier, Vendors, Protocol   string
	IntelTags, DNSResolvedIP, AssetType     string
	AlertCount                              int
	AnalysisStatus                          string
	IsFocused                               int
	ContentHash, UniqueHash                 string
}

func extractRow(row []string, headerMap map[string]int) *alertRow {
	v := &alertRow{}
	get := func(name string, fallbacks ...string) string {
		if idx, ok := headerMap[name]; ok && idx < len(row) {
			val := strings.TrimSpace(row[idx])
			if val != "" {
				return val
			}
		}
		for _, fb := range fallbacks {
			if idx, ok := headerMap[fb]; ok && idx < len(row) {
				return strings.TrimSpace(row[idx])
			}
		}
		return ""
	}

	v.DeviceID = get("设备ID")
	v.FirstAlertTime = get("首次告警时间")
	v.LastAlertTime = get("最近告警时间")
	v.SourceIP = get("源IP")
	v.Target = get("外联目标", "目标")
	v.TargetType = get("目标类型")
	v.Port = get("端口", "外联端口")
	v.ThreatType = get("威胁类型")
	v.ThreatLevel = get("威胁等级")
	v.StdAptOrg = get("标准APT组织")
	v.AptOrg = get("原始APT组织", "APT组织")
	v.AptOrgTier = get("APT分级", "APT组织分类")

	ac := get("告警次数")
	if ac != "" {
		fmt.Sscanf(ac, "%d", &v.AlertCount)
	}
	if v.AlertCount == 0 {
		v.AlertCount = 1
	}

	v.Vendors = get("厂商")
	v.Protocol = get("协议")
	v.IntelTags = get("情报标签")
	v.DNSResolvedIP = get("DNS解析IP")
	v.AssetType = get("资产类型")
	v.AnalysisStatus = get("研判状态")

	focused := get("重点关注")
	if focused == "是" || focused == "true" || focused == "1" {
		v.IsFocused = 1
	}

	v.ContentHash = computeContentHash(v)
	v.UniqueHash = fmt.Sprintf("%s-%s-%s-%s", v.DeviceID, v.Target, v.Port, v.ThreatType)

	return v
}

func computeContentHash(v *alertRow) string {
	key := fmt.Sprintf("%s|%s|%s|%s|%s|%s|%s|%s|%s",
		v.DeviceID, v.FirstAlertTime, v.LastAlertTime,
		v.SourceIP, v.Target, v.Port, v.ThreatType, v.ThreatLevel, v.StdAptOrg)
	h := sha256.Sum256([]byte(key))
	return hex.EncodeToString(h[:])
}

func (s *ImportService) updateImportStatus(id int, status string, inserted, skipped, failed, total, parsed int, log string) {
	s.DB.Exec(
		"UPDATE imports SET status=$1, rows_inserted=$2, rows_skipped=$3, rows_failed=$4, total_rows=$5, parsed_rows=$6, log=$7 WHERE id=$8",
		status, inserted, skipped, failed, total, parsed, log, id,
	)
}

// GetImport 获取导入状态
func (s *ImportService) GetImport(id int) (map[string]interface{}, error) {
	var idVal int
	var sourceFile, status, log, fileHash sql.NullString
	var totalRows, parsedRows, rowsInserted, rowsSkipped, rowsFailed, queuePos sql.NullInt64
	var importedAt sql.NullTime

	err := s.DB.QueryRow(
		"SELECT id, source_file, status, total_rows, parsed_rows, rows_inserted, rows_skipped, rows_failed, log, file_hash, queue_position, imported_at FROM imports WHERE id = $1",
		id,
	).Scan(&idVal, &sourceFile, &status, &totalRows, &parsedRows,
		&rowsInserted, &rowsSkipped, &rowsFailed, &log, &fileHash, &queuePos, &importedAt)
	if err != nil {
		return nil, err
	}

	return map[string]interface{}{
		"id":             idVal,
		"source_file":    nullString(sourceFile),
		"status":         nullString(status),
		"total_rows":     nullInt64(totalRows),
		"parsed_rows":    nullInt64(parsedRows),
		"rows_inserted":  nullInt64(rowsInserted),
		"rows_skipped":   nullInt64(rowsSkipped),
		"rows_failed":    nullInt64(rowsFailed),
		"log":            nullString(log),
		"file_hash":      nullString(fileHash),
		"queue_position": nullInt64(queuePos),
		"imported_at":    nullTime(importedAt),
	}, nil
}

func nullString(s sql.NullString) string {
	if s.Valid {
		return s.String
	}
	return ""
}
func nullInt64(s sql.NullInt64) int {
	if s.Valid {
		return int(s.Int64)
	}
	return 0
}
func nullTime(s sql.NullTime) string {
	if s.Valid {
		return s.Time.Format("2006-01-02 15:04:05")
	}
	return ""
}

// ListImports 获取导入列表
func (s *ImportService) ListImports() ([]map[string]interface{}, error) {
	var idVal int
	var sourceFile, status, log, fileHash sql.NullString
	var totalRows, parsedRows, rowsInserted, rowsSkipped, rowsFailed, queuePos sql.NullInt64
	var importedAt sql.NullTime

	rows, err := s.DB.Query(
		"SELECT id, source_file, status, total_rows, parsed_rows, rows_inserted, rows_skipped, rows_failed, log, file_hash, queue_position, imported_at FROM imports ORDER BY imported_at DESC",
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	results := make([]map[string]interface{}, 0)
	for rows.Next() {
		if err := rows.Scan(&idVal, &sourceFile, &status, &totalRows, &parsedRows, &rowsInserted, &rowsSkipped, &rowsFailed, &log, &fileHash, &queuePos, &importedAt); err != nil {
			continue
		}
		results = append(results, map[string]interface{}{
			"id":             idVal,
			"source_file":    nullString(sourceFile),
			"status":         nullString(status),
			"total_rows":     nullInt64(totalRows),
			"parsed_rows":    nullInt64(parsedRows),
			"rows_inserted":  nullInt64(rowsInserted),
			"rows_skipped":   nullInt64(rowsSkipped),
			"rows_failed":    nullInt64(rowsFailed),
			"log":            nullString(log),
			"file_hash":      nullString(fileHash),
			"queue_position": nullInt64(queuePos),
			"imported_at":    nullTime(importedAt),
		})
	}
	return results, nil
}

// GetImportSheets 获取导入的 Sheet 列表
func (s *ImportService) GetImportSheets(importID int) ([]map[string]interface{}, error) {
	rows, err := s.DB.Query(
		"SELECT id, sheet_name, sheet_index, header_row, headers_json, row_count, parsed_rows, raw_rows, failed_rows, status, created_at FROM import_sheets WHERE import_id = $1 ORDER BY sheet_index",
		importID,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	columns, _ := rows.Columns()
	results := make([]map[string]interface{}, 0)
	for rows.Next() {
		vals := make([]interface{}, len(columns))
		valPtrs := make([]interface{}, len(columns))
		for i := range vals {
			valPtrs[i] = &vals[i]
		}
		rows.Scan(valPtrs...)
		row := make(map[string]interface{})
		for i, col := range columns {
			row[col] = vals[i]
		}
		results = append(results, row)
	}
	return results, nil
}

// GetImportRows 获取导入的行明细（支持按 status_group 过滤）
func (s *ImportService) GetImportRows(importID int, sheetID int, statusGroup string, page, pageSize int) ([]map[string]interface{}, int64) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 {
		pageSize = 50
	}

	where := "WHERE ir.import_id = $1"
	args := []interface{}{importID}
	argIdx := 2

	if sheetID > 0 {
		where += fmt.Sprintf(" AND ir.import_sheet_id = $%d", argIdx)
		args = append(args, sheetID)
		argIdx++
	}

	switch statusGroup {
	case "parsed":
		where += fmt.Sprintf(" AND ir.parse_status = $%d", argIdx)
		args = append(args, "parsed")
		argIdx++
	case "skipped_duplicate":
		where += fmt.Sprintf(" AND ir.parse_status = $%d", argIdx)
		args = append(args, "skipped_duplicate")
		argIdx++
	case "raw_only":
		where += fmt.Sprintf(" AND ir.parse_status = $%d", argIdx)
		args = append(args, "raw_only")
		argIdx++
	case "failed":
		where += fmt.Sprintf(" AND ir.parse_status = $%d", argIdx)
		args = append(args, "failed")
		argIdx++
	}

	// Count
	var total int64
	countSQL := fmt.Sprintf("SELECT COUNT(*) FROM import_rows ir %s", where)
	if err := s.DB.QueryRow(countSQL, args...).Scan(&total); err != nil {
		return []map[string]interface{}{}, 0
	}

	// Query rows
	querySQL := fmt.Sprintf("SELECT ir.* FROM import_rows ir %s ORDER BY ir.excel_row_number ASC LIMIT $%d OFFSET $%d", where, argIdx, argIdx+1)
	args = append(args, pageSize, (page-1)*pageSize)

	rows, err := s.DB.Query(querySQL, args...)
	if err != nil {
		return []map[string]interface{}{}, 0
	}
	defer rows.Close()

	columns, err := rows.Columns()
	if err != nil {
		return []map[string]interface{}{}, 0
	}
	results := make([]map[string]interface{}, 0)
	for rows.Next() {
		vals := make([]interface{}, len(columns))
		valPtrs := make([]interface{}, len(columns))
		for i := range vals {
			valPtrs[i] = &vals[i]
		}
		if err := rows.Scan(valPtrs...); err != nil {
			continue
		}
		row := make(map[string]interface{})
		for i, col := range columns {
			row[col] = vals[i]
		}
		results = append(results, row)
	}
	return results, total
}

// GetImportFailures 导出失败行为 CSV
func (s *ImportService) GetImportFailures(importID int, failureType string) (string, [][]string, error) {
	var where string
	switch failureType {
	case "skipped":
		where = "ir.parse_status = 'skipped_duplicate'"
	case "raw_only":
		where = "ir.parse_status = 'raw_only'"
	default:
		where = "ir.parse_status = 'failed'"
	}

	query := fmt.Sprintf(`
		SELECT ir.excel_row_number, ir.sheet_name, ir.parse_status, ir.parse_error,
			   ir.raw_json
		FROM import_rows ir
		WHERE ir.import_id = $1 AND %s
		ORDER BY ir.excel_row_number ASC
	`, where)

	rows, err := s.DB.Query(query, importID)
	if err != nil {
		return "", nil, err
	}
	defer rows.Close()

	headers := []string{"row_number", "sheet_name", "status", "error", "raw_json"}
	data := [][]string{headers}
	for rows.Next() {
		var rowNum sql.NullInt64
		var sheetName, status, errMsg, rawJSON sql.NullString
		if err := rows.Scan(&rowNum, &sheetName, &status, &errMsg, &rawJSON); err != nil {
			continue
		}
		data = append(data, []string{
			nullInt64Ptr(rowNum),
			nullString(sheetName),
			nullString(status),
			nullString(errMsg),
			nullString(rawJSON),
		})
	}
	return "failures.csv", data, nil
}

func nullInt64Ptr(s sql.NullInt64) string {
	if s.Valid {
		return fmt.Sprintf("%d", s.Int64)
	}
	return ""
}

// DeleteImport 删除导入及关联数据（级联删除 alerts、import_rows、import_sheets）
func (s *ImportService) DeleteImport(id int) error {
	var filename sql.NullString
	s.DB.QueryRow("SELECT source_file FROM imports WHERE id = $1", id).Scan(&filename)

	// Cascade delete in dependency order
	if _, err := s.DB.Exec("DELETE FROM alerts WHERE import_id = $1", id); err != nil {
		return err
	}
	if _, err := s.DB.Exec("DELETE FROM import_rows WHERE import_id = $1", id); err != nil {
		return err
	}
	if _, err := s.DB.Exec("DELETE FROM import_sheets WHERE import_id = $1", id); err != nil {
		return err
	}
	if _, err := s.DB.Exec("DELETE FROM imports WHERE id = $1", id); err != nil {
		return err
	}

	if filename.Valid && filename.String != "" {
		os.Remove(filepath.Join(s.UploadDir, filename.String))
	}

	return nil
}

// DeleteAllImports removes all imported data (alerts + import rows/sheets + imports).
// Uses a transaction so partial failures leave data intact.
// Does NOT affect events, IOC notes, device tags, or config.
func (s *ImportService) DeleteAllImports() error {
	tx, err := s.DB.Begin()
	if err != nil {
		return fmt.Errorf("begin transaction: %w", err)
	}

	stmts := []string{
		"DELETE FROM alerts",
		"DELETE FROM import_rows",
		"DELETE FROM import_sheets",
		"DELETE FROM imports",
	}
	for _, sql := range stmts {
		if _, err := tx.Exec(sql); err != nil {
			tx.Rollback()
			return fmt.Errorf("delete: %w", err)
		}
	}

	return tx.Commit()
}

// ReprocessQueuedImports re-processes imports stuck in "queued" status.
func (s *ImportService) ReprocessQueuedImports() (int, error) {
	rows, err := s.DB.Query("SELECT id, source_file FROM imports WHERE status = 'queued'")
	if err != nil {
		return 0, err
	}
	defer rows.Close()

	count := 0
	for rows.Next() {
		var id int
		var filename string
		rows.Scan(&id, &filename)

		filePath := filepath.Join(s.UploadDir, filename)
		if _, err := os.Stat(filePath); os.IsNotExist(err) {
			s.DB.Exec("UPDATE imports SET status = 'failed', log = 'file missing' WHERE id = $1", id)
			continue
		}

		s.queueMu.Lock()
		s.queuePos++
		s.queue <- id
		s.queueMu.Unlock()
		s.updateImportStatus(id, "queued", 0, 0, 0, 0, 0, "re-queued for processing")
		count++
	}
	return count, nil
}

// RepairImportMetadata re-parses raw JSON data from import_rows and updates alert metadata.
// This extracts fields like analysis_status and is_focused that may have been missing during import.
// Return keys match frontend expectation: total, repaired, skipped, errors.
func (s *ImportService) RepairImportMetadata(importID int) (map[string]int, error) {
	// Query raw_json from import_rows that have associated alerts
	rowRows, err := s.DB.Query(`
		SELECT ir.id, ir.raw_json, ir.alert_id
		FROM import_rows ir
		WHERE ir.import_id = $1 AND ir.alert_id IS NOT NULL AND ir.raw_json IS NOT NULL
	`, importID)
	if err != nil {
		return nil, err
	}
	defer rowRows.Close()

	stats := map[string]int{"total": 0, "repaired": 0, "skipped": 0, "errors": 0}

	for rowRows.Next() {
		var rowID, alertID int
		var rawJSON sql.NullString
		err := rowRows.Scan(&rowID, &rawJSON, &alertID)
		if err != nil {
			stats["skipped"]++
			continue
		}
		if !rawJSON.Valid || rawJSON.String == "" {
			stats["skipped"]++
			continue
		}

		stats["total"]++

		// Parse the raw JSON to extract additional fields
		var rawData map[string]interface{}
		if err := json.Unmarshal([]byte(rawJSON.String), &rawData); err != nil {
			stats["skipped"]++
			continue
		}

		// Extract analysis_status and is_focused from raw data
		analysisStatus, _ := rawData["研判状态"].(string)
		if analysisStatus == "" {
			if v, ok := rawData["analysis_status"].(string); ok {
				analysisStatus = v
			}
		}

		isFocused := 0
		for _, key := range []string{"重点关注", "is_focused"} {
			if v, ok := rawData[key]; ok {
				switch val := v.(type) {
				case string:
					if val == "是" || val == "true" || val == "1" {
						isFocused = 1
					}
				case bool:
					if val {
						isFocused = 1
					}
				case float64:
					if val > 0 {
						isFocused = 1
					}
				}
				if isFocused == 1 {
					break
				}
			}
		}

		// Extract other potentially missing fields
		sourceIP, _ := rawData["源IP"].(string)
		if sourceIP == "" {
			if v, ok := rawData["source_ip"].(string); ok {
				sourceIP = v
			}
		}

		assetType, _ := rawData["资产类型"].(string)
		if assetType == "" {
			if v, ok := rawData["asset_type"].(string); ok {
				assetType = v
			}
		}

		// Update the alert record
		_, err = s.DB.Exec(`
			UPDATE alerts
			SET analysis_status = $1, is_focused = $2, source_ip = COALESCE(NULLIF(source_ip,''), $3),
			    asset_type = COALESCE(NULLIF(asset_type,''), $4)
			WHERE id = $5
		`, analysisStatus, isFocused, sourceIP, assetType, alertID)
		if err != nil {
			stats["errors"]++
			continue
		}

		stats["repaired"]++
	}

	return stats, nil
}
