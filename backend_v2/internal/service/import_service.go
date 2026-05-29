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

type importProgress struct {
	inserted int
	skipped  int
	failed   int
	raw      int
	total    int
}

func (p importProgress) processedRows() int {
	return p.inserted + p.skipped + p.failed + p.raw
}

func finalImportStatus(p importProgress) string {
	issueRows := p.failed + p.raw
	goodRows := p.inserted + p.skipped
	if goodRows > 0 && issueRows == 0 {
		return "success"
	}
	if goodRows > 0 && issueRows > 0 {
		return "partial"
	}
	return "failed"
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
		s.DB.Exec("UPDATE imports SET status = 'processing', queue_position = NULL, log = $2 WHERE id = $1", id, "processing")
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
		"id":             id,
		"source_file":    filename,
		"status":         "queued",
		"queue_position": qp,
	}, nil
}

// processImport 后台处理单个导入（由 queueWorker 调用）
func (s *ImportService) processImport(id int, filename string) {
	filePath := filepath.Join(s.UploadDir, filename)

	// 使用 excelize 流式读取（OpenReader + Rows 迭代器）
	f, err := excelize.OpenFile(filePath)
	if err != nil {
		s.updateImportStatus(id, "failed", importProgress{}, fmt.Sprintf("open excel: %v", err))
		return
	}
	defer f.Close()

	sheets := f.GetSheetList()
	if len(sheets) == 0 {
		s.updateImportStatus(id, "failed", importProgress{}, "no sheets found")
		return
	}

	progress := importProgress{}

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

		// 批量插入（UNNEST 多数组并行展开，每 200 行攒一批）
		tx, stmt, err := beginImportBatch(s.DB)
		if err != nil {
			rows.Close()
			s.updateImportStatus(id, "failed", progress, fmt.Sprintf("prepare stmt: %v", err))
			return
		}

		batchRows := 0
		sheetRows := 0
		sheetRaw := 0
		sheetFailed := 0
		rowNum := 1
		var batch []batchEntry

		failBatch := func(message string) {
			stmt.Close()
			tx.Rollback()
			s.updateImportStatus(id, "failed", progress, message)
		}

		commitBatch := func(final bool) bool {
			res, err := s.flushBatch(s.DB, tx, batch, id, sheetID, filename, sheetName)
			if err != nil {
				stmt.Close()
				tx.Rollback()
				s.updateImportStatus(id, "failed", progress, fmt.Sprintf("flush batch: %v", err))
				return false
			}
			progress.inserted += res.inserted
			progress.skipped += res.skipped
			progress.failed += res.failed
			sheetFailed += res.failed
			batch = nil
			stmt.Close()
			if err := tx.Commit(); err != nil {
				s.updateImportStatus(id, "failed", progress, fmt.Sprintf("commit batch: %v", err))
				return false
			}
			s.DB.Exec("UPDATE import_sheets SET parsed_rows = $1, raw_rows = $2, failed_rows = $3, status = 'processing' WHERE id = $4", sheetRows-sheetRaw-sheetFailed, sheetRaw, sheetFailed, sheetID)
			s.updateImportProgress(id, progress, fmt.Sprintf("processing: %d rows", progress.processedRows()))
			batchRows = 0
			if final {
				return true
			}
			tx, stmt, err = beginImportBatch(s.DB)
			if err != nil {
				s.updateImportStatus(id, "failed", progress, fmt.Sprintf("prepare stmt: %v", err))
				return false
			}
			return true
		}

		for rows.Next() {
			row, err := rows.Columns()
			if err != nil {
				continue
			}
			rowNum++
			progress.total++
			sheetRows++

			vals := extractRow(row, headerMap)
			rawJSON := marshalImportRow(vals)
			if missing := missingRequiredFields(vals); missing != "" {
				if err := writeRawOnlyRow(tx, id, sheetID, filename, rowNum, sheetName, missing, rawJSON); err != nil {
					failBatch(fmt.Sprintf("write import row: %v", err))
					rows.Close()
					return
				}
				progress.raw++
				sheetRaw++
				continue
			}

			batch = append(batch, batchEntry{
				DeviceID: vals.DeviceID, FirstAlertTime: vals.FirstAlertTime,
				LastAlertTime: vals.LastAlertTime, SourceIP: vals.SourceIP,
				Target: vals.Target, TargetType: vals.TargetType, Port: vals.Port,
				ThreatType: vals.ThreatType, ThreatLevel: vals.ThreatLevel,
				StdAptOrg: vals.StdAptOrg, AptOrg: vals.AptOrg,
				AptOrgTier: vals.AptOrgTier, AlertCount: vals.AlertCount,
				Vendors: vals.Vendors, Protocol: vals.Protocol,
				IntelTags: vals.IntelTags, DNSResolvedIP: vals.DNSResolvedIP,
				AssetType: vals.AssetType, AnalysisStatus: vals.AnalysisStatus,
				IsFocused: vals.IsFocused, ContentHash: vals.ContentHash,
				UniqueHash: vals.UniqueHash, RowNum: rowNum,
			})
			batchRows++

			if batchRows >= 200 && !commitBatch(false) {
				rows.Close()
				return
			}
		}
		rows.Close()
		// 最终 commit：刷新剩余 batch
		if !commitBatch(true) {
			return
		}

		s.DB.Exec("UPDATE import_sheets SET status = 'completed', parsed_rows = $1, row_count = $2, raw_rows = $3, failed_rows = $4 WHERE id = $5", sheetRows-sheetRaw-sheetFailed, sheetRows, sheetRaw, sheetFailed, sheetID)
	}

	log := fmt.Sprintf("导入完成: 成功 %d, 跳过 %d, 缺字段 %d, 失败 %d", progress.inserted, progress.skipped, progress.raw, progress.failed)
	s.updateImportStatus(id, finalImportStatus(progress), progress, log)
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

// batchEntry 累积用于批量 INSERT
type batchEntry struct {
	DeviceID, FirstAlertTime, LastAlertTime string
	SourceIP, Target, TargetType, Port      string
	ThreatType, ThreatLevel, StdAptOrg      string
	AptOrg, AptOrgTier, Vendors, Protocol   string
	IntelTags, DNSResolvedIP, AssetType     string
	AnalysisStatus                          string
	IsFocused                               int
	AlertCount                              int
	ContentHash, UniqueHash                 string
	RowNum                                  int
}

type flushResult struct {
	inserted, skipped, failed int
}

func (s *ImportService) flushBatch(db *sql.DB, tx *sql.Tx, batch []batchEntry, id, sheetID int, filename, sheetName string) (flushResult, error) {
	var res flushResult
	if len(batch) == 0 {
		return res, nil
	}

	// 批量 INSERT alerts (UNNEST 多数组并行展开)
	// 去重：先过滤掉已存在的 content_hash
	existingHashes := map[string]bool{}
	idRows, _ := tx.Query(
		"SELECT content_hash FROM alerts WHERE content_hash = ANY($1::text[])",
		pqArray(batchStrings(batch, "ContentHash")),
	)
	if idRows != nil {
		defer idRows.Close()
		for idRows.Next() {
			var h string
			idRows.Scan(&h)
			existingHashes[h] = true
		}
	}

	deduped := make([]batchEntry, 0, len(batch))
	for _, e := range batch {
		if !existingHashes[e.ContentHash] {
			deduped = append(deduped, e)
		}
	}
	if len(deduped) == 0 {
		res.skipped = len(batch)
		return res, nil
	}

	_, err := tx.Exec(`
		INSERT INTO alerts (
			device_id, first_alert_time, last_alert_time, source_ip, target,
			target_type, port, threat_type, threat_level, std_apt_org, apt_org,
			apt_org_tier, alert_count, vendors, protocol, intel_tags, dns_resolved_ip,
			down_traffic, up_traffic, asset_type, source_file, imported_at,
			analysis_status, is_focused, import_id, import_sheet_id, excel_row_number,
			sheet_name, content_hash, unique_hash
		)
		SELECT unnest($1::text[]), unnest($2::text[])::timestamp, unnest($3::text[])::timestamp,
			unnest($4::text[]), unnest($5::text[]), unnest($6::text[]),
			unnest($7::text[]), unnest($8::text[]), unnest($9::text[]),
			unnest($10::text[]), unnest($11::text[]), unnest($12::text[]),
			unnest($13::int[]), unnest($14::text[]), unnest($15::text[]),
			unnest($16::text[]), unnest($17::text[]),
			NULL, NULL,
			unnest($18::text[]), $19::text, NOW(),
			unnest($20::text[]), unnest($21::int[]), $22::int, $23::int,
			unnest($24::int[]),
			$25, unnest($26::text[]), unnest($27::text[])
	`,
		pqArray(batchDeviceIDs(deduped)), pqArray(batchTimes(deduped, true)), pqArray(batchTimes(deduped, false)),
		pqArray(batchStrings(deduped, "SourceIP")), pqArray(batchStrings(deduped, "Target")),
		pqArray(batchStrings(deduped, "TargetType")), pqArray(batchStrings(deduped, "Port")),
		pqArray(batchStrings(deduped, "ThreatType")), pqArray(batchStrings(deduped, "ThreatLevel")),
		pqArray(batchStrings(deduped, "StdAptOrg")), pqArray(batchStrings(deduped, "AptOrg")),
		pqArray(batchStrings(deduped, "AptOrgTier")), pqIntArray(batchAlertCounts(deduped)),
		pqArray(batchStrings(deduped, "Vendors")), pqArray(batchStrings(deduped, "Protocol")),
		pqArray(batchStrings(deduped, "IntelTags")), pqArray(batchStrings(deduped, "DNSResolvedIP")),
		pqArray(batchStrings(deduped, "AssetType")), filename,
		pqArray(batchStrings(deduped, "AnalysisStatus")), pqIntArray(batchIsFocused(deduped)),
		id, sheetID,
		pqIntArray(batchRowNums(deduped)),
		sheetName,
		pqArray(batchStrings(deduped, "ContentHash")), pqArray(batchStrings(deduped, "UniqueHash")),
	)
	if err != nil {
		tx.Rollback()
		return res, fmt.Errorf("batch insert: %w", err)
	}

	// 批量取回新插入的 alert ID
	idRows2, _ := tx.Query(`
		SELECT a.id, a.content_hash
		FROM alerts a
		JOIN unnest($1::text[]) AS b(content_hash) ON a.content_hash = b.content_hash
		WHERE a.import_id = $2
		ORDER BY a.id DESC
	`, pqArray(batchStrings(deduped, "ContentHash")), id)
	idMap := map[string]int64{}
	if idRows2 != nil {
		defer idRows2.Close()
		for idRows2.Next() {
			var aid int64
			var hash string
			idRows2.Scan(&aid, &hash)
			if _, exists := idMap[hash]; !exists {
				idMap[hash] = aid
			}
		}
	}

	// 逐行写 import_rows（在事务内）— 只写 deduped 行
	for _, e := range deduped {
		alertID, ok := idMap[e.ContentHash]
		if ok {
			tx.Exec(
				"INSERT INTO import_rows (import_id, import_sheet_id, source_file, excel_row_number, sheet_name, parse_status, raw_json, alert_id, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
				id, sheetID, filename, e.RowNum, sheetName, "parsed", marshalAlertRow(&e), alertID, time.Now(),
			)
			res.inserted++
		} else {
			tx.Exec(
				"INSERT INTO import_rows (import_id, import_sheet_id, source_file, excel_row_number, sheet_name, parse_status, raw_json, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
				id, sheetID, filename, e.RowNum, sheetName, "skipped_duplicate", marshalAlertRow(&e), time.Now(),
			)
			res.skipped++
		}
	}
	return res, nil
}

func batchRowNums(b []batchEntry) []int {
	r := make([]int, len(b))
	for i, e := range b {
		r[i] = e.RowNum
	}
	return r
}

func batchDeviceIDs(b []batchEntry) []string {
	r := make([]string, len(b))
	for i, e := range b {
		r[i] = e.DeviceID
	}
	return r
}
func batchTimes(b []batchEntry, first bool) []string {
	r := make([]string, len(b))
	if first {
		for i, e := range b {
			r[i] = e.FirstAlertTime
		}
	} else {
		for i, e := range b {
			r[i] = e.LastAlertTime
		}
	}
	return r
}
func batchStrings(b []batchEntry, field string) []string {
	r := make([]string, len(b))
	for i, e := range b {
		switch field {
		case "SourceIP":
			r[i] = e.SourceIP
		case "Target":
			r[i] = e.Target
		case "TargetType":
			r[i] = e.TargetType
		case "Port":
			r[i] = e.Port
		case "ThreatType":
			r[i] = e.ThreatType
		case "ThreatLevel":
			r[i] = e.ThreatLevel
		case "StdAptOrg":
			r[i] = e.StdAptOrg
		case "AptOrg":
			r[i] = e.AptOrg
		case "AptOrgTier":
			r[i] = e.AptOrgTier
		case "Vendors":
			r[i] = e.Vendors
		case "Protocol":
			r[i] = e.Protocol
		case "IntelTags":
			r[i] = e.IntelTags
		case "DNSResolvedIP":
			r[i] = e.DNSResolvedIP
		case "AssetType":
			r[i] = e.AssetType
		case "AnalysisStatus":
			r[i] = e.AnalysisStatus
		case "ContentHash":
			r[i] = e.ContentHash
		case "UniqueHash":
			r[i] = e.UniqueHash
		}
	}
	return r
}
func batchAlertCounts(b []batchEntry) []int {
	r := make([]int, len(b))
	for i, e := range b {
		r[i] = e.AlertCount
	}
	return r
}
func batchIsFocused(b []batchEntry) []int {
	r := make([]int, len(b))
	for i, e := range b {
		r[i] = e.IsFocused
	}
	return r
}
func marshalAlertRow(e *batchEntry) string {
	rawJSON, _ := json.Marshal(map[string]interface{}{
		"device_id": e.DeviceID, "first_alert_time": e.FirstAlertTime,
		"last_alert_time": e.LastAlertTime, "source_ip": e.SourceIP,
		"target": e.Target, "target_type": e.TargetType, "port": e.Port,
		"threat_type": e.ThreatType, "threat_level": e.ThreatLevel,
		"std_apt_org": e.StdAptOrg, "apt_org": e.AptOrg,
		"apt_org_tier": e.AptOrgTier, "alert_count": e.AlertCount,
		"vendors": e.Vendors, "protocol": e.Protocol,
		"intel_tags": e.IntelTags, "dns_resolved_ip": e.DNSResolvedIP,
		"asset_type": e.AssetType, "analysis_status": e.AnalysisStatus,
		"is_focused": e.IsFocused,
	})
	return string(rawJSON)
}

// pqEscape escapes a value for PostgreSQL array literal.
func pqEscape(s string) string {
	if s == "" || strings.ContainsAny(s, `{}",\`) {
		return `"` + strings.ReplaceAll(s, `"`, `""`) + `"`
	}
	return s
}

func pqArray(s []string) string {
	elems := make([]string, len(s))
	for i, v := range s {
		elems[i] = pqEscape(v)
	}
	return "{" + strings.Join(elems, ",") + "}"
}
func pqIntArray(s []int) string {
	r := make([]string, len(s))
	for i, v := range s {
		r[i] = fmt.Sprintf("%d", v)
	}
	return "{" + strings.Join(r, ",") + "}"
}

// beginImportBatch 创建事务 + alert INSERT 语句。
// 不再预准备 import_rows 语句——行写入在 flushBatch 中批量完成。
func beginImportBatch(db *sql.DB) (*sql.Tx, *sql.Stmt, error) {
	tx, err := db.Begin()
	if err != nil {
		return nil, nil, err
	}

	alertStmt, err := tx.Prepare(`
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
		return nil, nil, err
	}

	return tx, alertStmt, nil
}

func writeRawOnlyRow(tx *sql.Tx, importID, sheetID int, filename string, rowNum int, sheetName, reason, rawJSON string) error {
	_, err := tx.Exec(
		"INSERT INTO import_rows (import_id, import_sheet_id, source_file, excel_row_number, sheet_name, parse_status, parse_error, raw_json, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
		importID, sheetID, filename, rowNum, sheetName, "raw_only", reason, rawJSON, time.Now(),
	)
	return err
}

func missingRequiredFields(v *alertRow) string {
	missing := make([]string, 0, 4)
	if v.DeviceID == "" {
		missing = append(missing, "device_id")
	}
	if v.SourceIP == "" {
		missing = append(missing, "source_ip")
	}
	if v.Target == "" {
		missing = append(missing, "target")
	}
	if v.FirstAlertTime == "" || v.LastAlertTime == "" {
		missing = append(missing, "alert_time")
	}
	if len(missing) == 0 {
		return ""
	}
	return "missing required fields: " + strings.Join(missing, ",")
}

func marshalImportRow(v *alertRow) string {
	rawJSON, _ := json.Marshal(map[string]interface{}{
		"device_id":        v.DeviceID,
		"first_alert_time": v.FirstAlertTime,
		"last_alert_time":  v.LastAlertTime,
		"source_ip":        v.SourceIP,
		"target":           v.Target,
		"target_type":      v.TargetType,
		"port":             v.Port,
		"threat_type":      v.ThreatType,
		"threat_level":     v.ThreatLevel,
		"std_apt_org":      v.StdAptOrg,
		"apt_org":          v.AptOrg,
		"apt_org_tier":     v.AptOrgTier,
		"alert_count":      v.AlertCount,
		"vendors":          v.Vendors,
		"protocol":         v.Protocol,
		"intel_tags":       v.IntelTags,
		"dns_resolved_ip":  v.DNSResolvedIP,
		"asset_type":       v.AssetType,
		"analysis_status":  v.AnalysisStatus,
		"is_focused":       v.IsFocused,
	})
	return string(rawJSON)
}

func (s *ImportService) updateImportStatus(id int, status string, progress importProgress, log string) {
	s.DB.Exec(
		"UPDATE imports SET status=$1, rows_inserted=$2, rows_skipped=$3, rows_failed=$4, raw_rows=$5, total_rows=$6, parsed_rows=$7, log=$8 WHERE id=$9",
		status, progress.inserted, progress.skipped, progress.failed, progress.raw, progress.total, progress.processedRows(), log, id,
	)
}

func (s *ImportService) updateImportProgress(id int, progress importProgress, log string) {
	s.DB.Exec(
		"UPDATE imports SET status='processing', rows_inserted=$1, rows_skipped=$2, rows_failed=$3, raw_rows=$4, parsed_rows=$5, log=$6 WHERE id=$7",
		progress.inserted, progress.skipped, progress.failed, progress.raw, progress.processedRows(), log, id,
	)
}

// GetImport 获取导入状态
func (s *ImportService) GetImport(id int) (map[string]interface{}, error) {
	var idVal int
	var sourceFile, status, log, fileHash sql.NullString
	var totalRows, parsedRows, rowsInserted, rowsSkipped, rowsFailed, rawRows, queuePos sql.NullInt64
	var importedAt sql.NullTime

	err := s.DB.QueryRow(
		"SELECT id, source_file, status, total_rows, parsed_rows, rows_inserted, rows_skipped, rows_failed, raw_rows, log, file_hash, queue_position, imported_at FROM imports WHERE id = $1",
		id,
	).Scan(&idVal, &sourceFile, &status, &totalRows, &parsedRows,
		&rowsInserted, &rowsSkipped, &rowsFailed, &rawRows, &log, &fileHash, &queuePos, &importedAt)
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
		"raw_rows":       nullInt64(rawRows),
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
	var totalRows, parsedRows, rowsInserted, rowsSkipped, rowsFailed, rawRows, queuePos sql.NullInt64
	var importedAt sql.NullTime

	rows, err := s.DB.Query(
		"SELECT id, source_file, status, total_rows, parsed_rows, rows_inserted, rows_skipped, rows_failed, raw_rows, log, file_hash, queue_position, imported_at FROM imports ORDER BY imported_at DESC",
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	results := make([]map[string]interface{}, 0)
	for rows.Next() {
		if err := rows.Scan(&idVal, &sourceFile, &status, &totalRows, &parsedRows, &rowsInserted, &rowsSkipped, &rowsFailed, &rawRows, &log, &fileHash, &queuePos, &importedAt); err != nil {
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
			"raw_rows":       nullInt64(rawRows),
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
		s.updateImportStatus(id, "queued", importProgress{}, "re-queued for processing")
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
