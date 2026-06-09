package repository

import (
	"database/sql"
	"strings"
)

type DeviceRepo struct {
	DB *sql.DB
}

func NewDeviceRepo(db *sql.DB) *DeviceRepo { return &DeviceRepo{DB: db} }

type DeviceItem struct {
	DeviceID   string   `json:"device_id"`
	AlertCount int      `json:"alert_count"`
	FirstSeen  string   `json:"first_seen"`
	LastSeen   string   `json:"last_seen"`
	DeviceTags []string `json:"device_tags"`
	EventCount int      `json:"event_count"`
	DeviceNote string   `json:"device_note"`
}

func (r *DeviceRepo) Query(keyword, tags string, page, pageSize int) ([]DeviceItem, int64, error) {
	switch {
	case tags != "" && keyword != "":
		return r.queryByTagAndKeyword(tags, keyword, page, pageSize)
	case tags != "":
		return r.queryByTag(tags, page, pageSize)
	case keyword != "":
		return r.queryByKeyword(keyword, page, pageSize)
	default:
		return r.queryAll(page, pageSize)
	}
}

func (r *DeviceRepo) queryByTagAndKeyword(tags, keyword string, page, pageSize int) ([]DeviceItem, int64, error) {
	items, err := r.queryDevices(`
		SELECT a.device_id, COUNT(*) as alert_count,
		       to_char(MIN(a.first_alert_time), 'YYYY-MM-DD HH24:MI:SS') as first_seen,
		       to_char(MAX(a.last_alert_time), 'YYYY-MM-DD HH24:MI:SS') as last_seen,
		       (SELECT STRING_AGG(t.name, ',') FROM device_tags dt2
		        INNER JOIN tags t ON t.id = dt2.tag_id
		        WHERE UPPER(dt2.device_id) = UPPER(a.device_id)) as device_tags,
		       (SELECT COUNT(DISTINCT event_id) FROM mined_event_devices WHERE device_id = a.device_id) as event_count
		FROM alerts a
		INNER JOIN device_tags dt ON UPPER(dt.device_id) = UPPER(a.device_id)
		INNER JOIN tags t ON t.id = dt.tag_id
		WHERE t.name IN (SELECT unnest(string_to_array($1, ','))) AND a.device_id LIKE $2
		GROUP BY a.device_id ORDER BY alert_count DESC LIMIT $3 OFFSET $4
	`, tags, "%"+keyword+"%", pageSize, (page-1)*pageSize)

	var total int64
	r.DB.QueryRow(`
		SELECT COUNT(DISTINCT a.device_id) FROM alerts a
		INNER JOIN device_tags dt ON UPPER(dt.device_id) = UPPER(a.device_id)
		INNER JOIN tags t ON t.id = dt.tag_id
		WHERE t.name IN (SELECT unnest(string_to_array($1, ','))) AND a.device_id LIKE $2
	`, tags, "%"+keyword+"%").Scan(&total)

	return items, total, err
}

func (r *DeviceRepo) queryByTag(tags string, page, pageSize int) ([]DeviceItem, int64, error) {
	items, err := r.queryDevices(`
		SELECT a.device_id, COUNT(*) as alert_count,
		       to_char(MIN(a.first_alert_time), 'YYYY-MM-DD HH24:MI:SS') as first_seen,
		       to_char(MAX(a.last_alert_time), 'YYYY-MM-DD HH24:MI:SS') as last_seen,
		       (SELECT STRING_AGG(t.name, ',') FROM device_tags dt2
		        INNER JOIN tags t ON t.id = dt2.tag_id
		        WHERE UPPER(dt2.device_id) = UPPER(a.device_id)) as device_tags,
		       (SELECT COUNT(DISTINCT event_id) FROM mined_event_devices WHERE device_id = a.device_id) as event_count
		FROM alerts a
		INNER JOIN device_tags dt ON UPPER(dt.device_id) = UPPER(a.device_id)
		INNER JOIN tags t ON t.id = dt.tag_id
		WHERE t.name IN (SELECT unnest(string_to_array($1, ',')))
		GROUP BY a.device_id ORDER BY alert_count DESC LIMIT $2 OFFSET $3
	`, tags, pageSize, (page-1)*pageSize)

	var total int64
	r.DB.QueryRow(`
		SELECT COUNT(DISTINCT a.device_id) FROM alerts a
		INNER JOIN device_tags dt ON UPPER(dt.device_id) = UPPER(a.device_id)
		INNER JOIN tags t ON t.id = dt.tag_id
		WHERE t.name IN (SELECT unnest(string_to_array($1, ',')))
	`, tags).Scan(&total)

	return items, total, err
}

func (r *DeviceRepo) queryByKeyword(keyword string, page, pageSize int) ([]DeviceItem, int64, error) {
	items, err := r.queryDevices(`
		SELECT a.device_id, COUNT(*) as alert_count,
		       to_char(MIN(a.first_alert_time), 'YYYY-MM-DD HH24:MI:SS') as first_seen,
		       to_char(MAX(a.last_alert_time), 'YYYY-MM-DD HH24:MI:SS') as last_seen,
		       (SELECT STRING_AGG(t.name, ',') FROM device_tags dt2
		        INNER JOIN tags t ON t.id = dt2.tag_id
		        WHERE UPPER(dt2.device_id) = UPPER(a.device_id)) as device_tags,
		       (SELECT COUNT(DISTINCT event_id) FROM mined_event_devices WHERE device_id = a.device_id) as event_count
		FROM alerts a
		WHERE a.device_id LIKE $1
		GROUP BY a.device_id ORDER BY alert_count DESC LIMIT $2 OFFSET $3
	`, "%"+keyword+"%", pageSize, (page-1)*pageSize)

	var total int64
	r.DB.QueryRow("SELECT COUNT(DISTINCT device_id) FROM alerts WHERE device_id LIKE $1", "%"+keyword+"%").Scan(&total)

	return items, total, err
}

func (r *DeviceRepo) queryAll(page, pageSize int) ([]DeviceItem, int64, error) {
	items, err := r.queryDevices(`
		SELECT a.device_id, COUNT(*) as alert_count,
		       to_char(MIN(a.first_alert_time), 'YYYY-MM-DD HH24:MI:SS') as first_seen,
		       to_char(MAX(a.last_alert_time), 'YYYY-MM-DD HH24:MI:SS') as last_seen,
		       (SELECT STRING_AGG(t.name, ',') FROM device_tags dt2
		        INNER JOIN tags t ON t.id = dt2.tag_id
		        WHERE UPPER(dt2.device_id) = UPPER(a.device_id)) as device_tags,
		       (SELECT COUNT(DISTINCT event_id) FROM mined_event_devices WHERE device_id = a.device_id) as event_count
		FROM alerts a
		GROUP BY a.device_id ORDER BY alert_count DESC LIMIT $1 OFFSET $2
	`, pageSize, (page-1)*pageSize)

	var total int64
	r.DB.QueryRow("SELECT COUNT(DISTINCT device_id) FROM alerts").Scan(&total)

	return items, total, err
}

func (r *DeviceRepo) queryDevices(query string, args ...interface{}) ([]DeviceItem, error) {
	rows, err := r.DB.Query(query, args...)
	if err != nil {
		return []DeviceItem{}, err
	}
	defer rows.Close()

	var items []DeviceItem
	for rows.Next() {
		var d DeviceItem
		var tagsStr sql.NullString
		rows.Scan(&d.DeviceID, &d.AlertCount, &d.FirstSeen, &d.LastSeen, &tagsStr, &d.EventCount)
		if tagsStr.Valid && tagsStr.String != "" {
			d.DeviceTags = splitCommaSep(tagsStr.String)
		} else {
			d.DeviceTags = []string{}
		}
		items = append(items, d)
	}
	if items == nil {
		items = []DeviceItem{}
	}
	return items, nil
}

func splitCommaSep(s string) []string {
	parts := strings.Split(s, ",")
	result := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			result = append(result, p)
		}
	}
	return result
}

func (r *DeviceRepo) AddDeviceTags(deviceID string, tagNames []string) error {
	for _, tagName := range tagNames {
		tagName = strings.TrimSpace(tagName)
		if tagName == "" {
			continue
		}
		var tagID int
		err := r.DB.QueryRow("SELECT id FROM tags WHERE name = $1", tagName).Scan(&tagID)
		if err == sql.ErrNoRows {
			err = r.DB.QueryRow(
				"INSERT INTO tags (name, color, is_permanent, created_at) VALUES ($1, $2, 0, NOW()) RETURNING id",
				tagName, "#409EFF").Scan(&tagID)
			if err != nil {
				return err
			}
		} else if err != nil {
			return err
		}
		_, err = r.DB.Exec(
			"INSERT INTO device_tags (device_id, tag_id, created_at) VALUES ($1, $2, NOW()) ON CONFLICT DO NOTHING",
			deviceID, tagID)
		if err != nil {
			return err
		}
	}
	return nil
}

func (r *DeviceRepo) RemoveDeviceTag(deviceID, tagName string) error {
	_, err := r.DB.Exec(`
		DELETE FROM device_tags dt USING tags t
		WHERE dt.tag_id = t.id AND dt.device_id = $1 AND t.name = $2`,
		deviceID, tagName)
	return err
}
