package repository

import (
	"database/sql"
	"encoding/json"
	"strings"
	"time"
)

type TagRepo struct {
	DB *sql.DB
}

func NewTagRepo(db *sql.DB) *TagRepo { return &TagRepo{DB: db} }

type Tag struct {
	ID          int    `json:"id"`
	Name        string `json:"name"`
	Color       string `json:"color"`
	IsPermanent bool   `json:"is_permanent"`
	BatchID     *int   `json:"batch_id"`
	CreatedAt   string `json:"created_at"`
	Note        string `json:"note"`
}

type TagBatch struct {
	ID                int      `json:"id"`
	BatchName         string   `json:"batch_name"`
	CreatedAt         string   `json:"created_at"`
	Note              string   `json:"note"`
	Status            string   `json:"status"`
	DeviceIDsSnapshot []string `json:"device_ids_snapshot"`
	Devices           []string `json:"devices"`
	DeviceCount       int      `json:"device_count"`
	TagName           string   `json:"tag_name"`
	Color             string   `json:"color"`
}

func (r *TagRepo) ListTags() ([]Tag, error) {
	rows, err := r.DB.Query("SELECT id, name, color, is_permanent = 1, batch_id, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS'), note FROM tags ORDER BY created_at DESC")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tags []Tag
	for rows.Next() {
		var t Tag
		var batchID sql.NullInt64
		rows.Scan(&t.ID, &t.Name, &t.Color, &t.IsPermanent, &batchID, &t.CreatedAt, &t.Note)
		if batchID.Valid {
			v := int(batchID.Int64)
			t.BatchID = &v
		}
		tags = append(tags, t)
	}
	if tags == nil {
		tags = []Tag{}
	}
	return tags, nil
}

func (r *TagRepo) ListBatches() ([]TagBatch, error) {
	rows, err := r.DB.Query(`
		SELECT tb.id, tb.batch_name, to_char(tb.created_at, 'YYYY-MM-DD HH24:MI:SS'), tb.note, tb.status,
			   tb.device_ids_snapshot, t.name, t.color
		FROM tag_batches tb
		LEFT JOIN tags t ON t.batch_id = tb.id
		ORDER BY tb.created_at DESC
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var batches []TagBatch
	for rows.Next() {
		var b TagBatch
		var snapshotJSON sql.NullString
		rows.Scan(&b.ID, &b.BatchName, &b.CreatedAt, &b.Note, &b.Status, &snapshotJSON, &b.TagName, &b.Color)
		if snapshotJSON.Valid {
			json.Unmarshal([]byte(snapshotJSON.String), &b.DeviceIDsSnapshot)
		}
		batches = append(batches, b)
	}
	// Return empty slice instead of nil for consistent JSON.
	if batches == nil {
		batches = []TagBatch{}
	}
	return batches, nil
}

func (r *TagRepo) CreateBatch(batchName, tagName, color string, devices []string, note string) (int, error) {
	tx, _ := r.DB.Begin()

	var batchID int
	err := tx.QueryRow(
		"INSERT INTO tag_batches (batch_name, created_at, note, status, device_ids_snapshot) VALUES ($1, $2, $3, 'active', $4) RETURNING id",
		batchName, time.Now(), note, toJSON(devices),
	).Scan(&batchID)
	if err != nil {
		tx.Rollback()
		return 0, err
	}

	var tagID int
	err = tx.QueryRow(
		"INSERT INTO tags (name, color, is_permanent, batch_id, created_at) VALUES ($1, $2, 0, $3, $4) RETURNING id",
		strings.TrimSpace(tagName), color, batchID, time.Now(),
	).Scan(&tagID)
	if err != nil {
		tx.Rollback()
		return 0, err
	}

	for _, d := range devices {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		tx.Exec("INSERT INTO device_tags (device_id, tag_id, created_at) VALUES (UPPER($1), $2, $3) ON CONFLICT DO NOTHING", d, tagID, time.Now())
	}

	tx.Commit()
	return batchID, nil
}

func (r *TagRepo) DeleteBatch(batchID int) error {
	_, err := r.DB.Exec("UPDATE tag_batches SET status = 'deleted' WHERE id = $1", batchID)
	return err
}

// RestoreBatch restores a deleted batch and returns the number of devices re-tagged.
func (r *TagRepo) RestoreBatch(batchID int) (int, error) {
	tx, err := r.DB.Begin()
	if err != nil {
		return 0, err
	}

	// Restore batch status
	if _, err := tx.Exec("UPDATE tag_batches SET status = 'active' WHERE id = $1", batchID); err != nil {
		tx.Rollback()
		return 0, err
	}

	// Count devices currently tagged with this batch's tag
	var count int
	err = tx.QueryRow(`
		SELECT COUNT(*) FROM device_tags dt
		JOIN tags t ON t.id = dt.tag_id
		WHERE t.batch_id = $1
	`, batchID).Scan(&count)
	if err != nil {
		tx.Rollback()
		return 0, err
	}

	tx.Commit()
	return count, nil
}

// RemoveBatchDevices removes specific devices from a batch's tags, returns count.
func (r *TagRepo) RemoveBatchDevices(batchID int, deviceIDs []string) (int, error) {
	count := 0
	for _, d := range deviceIDs {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		res, err := r.DB.Exec(`
			DELETE FROM device_tags
			WHERE tag_id IN (SELECT id FROM tags WHERE batch_id = $1)
			  AND device_id = UPPER($2)
		`, batchID, d)
		if err != nil {
			return count, err
		}
		rows, _ := res.RowsAffected()
		count += int(rows)
	}
	return count, nil
}

func (r *TagRepo) GetDeviceTags(deviceID string) ([]Tag, error) {
	rows, err := r.DB.Query(`
		SELECT t.id, t.name, t.color
		FROM device_tags dt JOIN tags t ON t.id = dt.tag_id
		WHERE UPPER(dt.device_id) = UPPER($1)
		  AND (t.batch_id IS NULL OR EXISTS (
			  SELECT 1 FROM tag_batches tb WHERE tb.id = t.batch_id AND tb.status = 'active'
		  ))
		ORDER BY t.name
	`, deviceID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tags []Tag
	for rows.Next() {
		var t Tag
		rows.Scan(&t.ID, &t.Name, &t.Color)
		tags = append(tags, t)
	}
	return tags, nil
}

func (r *TagRepo) AddDeviceTag(deviceID, tagName, color string) error {
	tx, _ := r.DB.Begin()

	var tagID int
	err := tx.QueryRow("SELECT id FROM tags WHERE name = $1", tagName).Scan(&tagID)
	if err != nil {
		err = tx.QueryRow(
			"INSERT INTO tags (name, color, is_permanent, created_at) VALUES ($1, $2, 1, $3) RETURNING id",
			strings.TrimSpace(tagName), color, time.Now(),
		).Scan(&tagID)
		if err != nil {
			tx.Rollback()
			return err
		}
	}

	tx.Exec("INSERT INTO device_tags (device_id, tag_id, created_at) VALUES (UPPER($1), $2, $3) ON CONFLICT DO NOTHING", deviceID, tagID, time.Now())
	tx.Commit()
	return nil
}

func (r *TagRepo) RemoveDeviceTag(deviceID string, tagID int) error {
	_, err := r.DB.Exec("DELETE FROM device_tags WHERE device_id = UPPER($1) AND tag_id = $2", deviceID, tagID)
	return err
}

func (r *TagRepo) BatchTagDevices(devices []string, tagName, color string) (int, error) {
	tx, _ := r.DB.Begin()

	var tagID int
	err := tx.QueryRow("SELECT id FROM tags WHERE name = $1", tagName).Scan(&tagID)
	if err != nil {
		err = tx.QueryRow(
			"INSERT INTO tags (name, color, is_permanent, created_at) VALUES ($1, $2, 1, $3) RETURNING id",
			strings.TrimSpace(tagName), color, time.Now(),
		).Scan(&tagID)
		if err != nil {
			tx.Rollback()
			return 0, err
		}
	}

	count := 0
	for _, d := range devices {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		_, err := tx.Exec("INSERT INTO device_tags (device_id, tag_id, created_at) VALUES (UPPER($1), $2, $3) ON CONFLICT DO NOTHING", d, tagID, time.Now())
		if err == nil {
			count++
		}
	}

	tx.Commit()
	return count, nil
}

func (r *TagRepo) UpdateTagColor(tagID int, color string) error {
	_, err := r.DB.Exec("UPDATE tags SET color = $1 WHERE id = $2", color, tagID)
	return err
}

func (r *TagRepo) BatchRemoveDeviceTags(reqs []struct {
	DeviceID string `json:"device_id"`
	TagID    int    `json:"tag_id"`
}) error {
	for _, req := range reqs {
		if _, err := r.DB.Exec(
			"DELETE FROM device_tags WHERE device_id = UPPER($1) AND tag_id = $2",
			req.DeviceID, req.TagID,
		); err != nil {
			return err
		}
	}
	return nil
}

// BatchRemoveDeviceTagsByTagID removes multiple devices from a single tag, returns count.
func (r *TagRepo) BatchRemoveDeviceTagsByTagID(tagID int, deviceIDs []string) (int, error) {
	count := 0
	for _, d := range deviceIDs {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		res, err := r.DB.Exec(
			"DELETE FROM device_tags WHERE device_id = UPPER($1) AND tag_id = $2",
			d, tagID,
		)
		if err != nil {
			return count, err
		}
		rows, _ := res.RowsAffected()
		count += int(rows)
	}
	return count, nil
}

func (r *TagRepo) GetBatchDetail(batchID int) (*TagBatch, error) {
	var b TagBatch
	var snapshotJSON sql.NullString
	err := r.DB.QueryRow(`
		SELECT tb.id, tb.batch_name, to_char(tb.created_at, 'YYYY-MM-DD HH24:MI:SS'),
		       tb.note, tb.status, tb.device_ids_snapshot, t.name, t.color
		FROM tag_batches tb
		LEFT JOIN tags t ON t.batch_id = tb.id
		WHERE tb.id = $1
	`, batchID).Scan(&b.ID, &b.BatchName, &b.CreatedAt, &b.Note, &b.Status, &snapshotJSON, &b.TagName, &b.Color)
	if err != nil {
		return nil, err
	}
	if snapshotJSON.Valid {
		json.Unmarshal([]byte(snapshotJSON.String), &b.DeviceIDsSnapshot)
	}

	// Get current device list from device_tags
	tagRows, err := r.DB.Query(`
		SELECT dt.device_id FROM device_tags dt
		JOIN tags t ON t.id = dt.tag_id
		WHERE t.batch_id = $1
	`, batchID)
	if err == nil {
		defer tagRows.Close()
		var devices []string
		for tagRows.Next() {
			var d string
			tagRows.Scan(&d)
			devices = append(devices, d)
		}
		b.DeviceIDsSnapshot = devices
		b.Devices = devices
		b.DeviceCount = len(devices)
	}
	return &b, nil
}

func toJSON(arr []string) string {
	if len(arr) == 0 {
		return "[]"
	}
	data, _ := json.Marshal(arr)
	return string(data)
}
