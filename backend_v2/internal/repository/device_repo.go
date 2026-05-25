package repository

import (
	"database/sql"
)

type DeviceRepo struct {
	DB *sql.DB
}

func NewDeviceRepo(db *sql.DB) *DeviceRepo { return &DeviceRepo{DB: db} }

type DeviceItem struct {
	DeviceID   string `json:"device_id"`
	AlertCount int    `json:"alert_count"`
	FirstSeen  string `json:"first_seen"`
	LastSeen   string `json:"last_seen"`
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
		       to_char(MAX(a.last_alert_time), 'YYYY-MM-DD HH24:MI:SS') as last_seen
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
		       to_char(MAX(a.last_alert_time), 'YYYY-MM-DD HH24:MI:SS') as last_seen
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
		       to_char(MAX(a.last_alert_time), 'YYYY-MM-DD HH24:MI:SS') as last_seen
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
		       to_char(MAX(a.last_alert_time), 'YYYY-MM-DD HH24:MI:SS') as last_seen
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
		rows.Scan(&d.DeviceID, &d.AlertCount, &d.FirstSeen, &d.LastSeen)
		items = append(items, d)
	}
	if items == nil {
		items = []DeviceItem{}
	}
	return items, nil
}
