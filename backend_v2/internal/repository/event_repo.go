package repository

import (
	"database/sql"
	"strings"
	"time"
)

type EventRepo struct {
	DB *sql.DB
}

func NewEventRepo(db *sql.DB) *EventRepo {
	return &EventRepo{DB: db}
}

type Event struct {
	ID      int       `json:"id"`
	Name    string    `json:"event_name"`
	Color   string    `json:"color"`
	Status  string    `json:"status"`
	MinedAt time.Time `json:"mined_at"`
	Note    string    `json:"note"`
}

type EventDetail struct {
	ID        int       `json:"id"`
	Name      string    `json:"event_name"`
	Color     string    `json:"color"`
	Status    string    `json:"status"`
	MinedAt   string    `json:"mined_at"`
	Note      string    `json:"note"`
	Devices   []string  `json:"devices"`
	IOCs      []IOC     `json:"iocs"`
	Followups []Followup `json:"followups"`
}

type IOC struct {
	Target string `json:"target"`
	Port   string `json:"port"`
}

type Followup struct {
	ID         int    `json:"id"`
	ActionType string `json:"action_type"`
	CreatedAt  string `json:"created_at"`
	Note       string `json:"note"`
}

func (r *EventRepo) ListEvents(statusFilter string) ([]Event, error) {
	query := "SELECT id, event_name, color, status, mined_at, note FROM mined_events"
	args := []interface{}{}
	if statusFilter != "" && statusFilter != "all" {
		query += " WHERE status = $1"
		args = append(args, statusFilter)
	}
	query += " ORDER BY mined_at DESC"

	rows, err := r.DB.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var events []Event
	for rows.Next() {
		var e Event
		rows.Scan(&e.ID, &e.Name, &e.Color, &e.Status, &e.MinedAt, &e.Note)
		events = append(events, e)
	}
	return events, nil
}

func (r *EventRepo) GetEvent(id int) (*EventDetail, error) {
	detail := &EventDetail{}
	var minedAt time.Time
	err := r.DB.QueryRow(
		"SELECT id, event_name, color, status, mined_at, note FROM mined_events WHERE id = $1", id,
	).Scan(&detail.ID, &detail.Name, &detail.Color, &detail.Status, &minedAt, &detail.Note)
	if err != nil {
		return nil, err
	}
	detail.MinedAt = minedAt.Format("2006-01-02 15:04:05")

	devRows, _ := r.DB.Query("SELECT device_id FROM mined_event_devices WHERE event_id = $1", id)
	defer devRows.Close()
	for devRows.Next() {
		var d string
		devRows.Scan(&d)
		detail.Devices = append(detail.Devices, d)
	}

	iocRows, _ := r.DB.Query("SELECT target, port FROM mined_event_iocs WHERE event_id = $1", id)
	defer iocRows.Close()
	for iocRows.Next() {
		var ioc IOC
		iocRows.Scan(&ioc.Target, &ioc.Port)
		detail.IOCs = append(detail.IOCs, ioc)
	}

	fRows, _ := r.DB.Query("SELECT id, action_type, created_at, note FROM event_followups WHERE event_id = $1 ORDER BY created_at ASC", id)
	defer fRows.Close()
	for fRows.Next() {
		var f Followup
		var ca time.Time
		fRows.Scan(&f.ID, &f.ActionType, &ca, &f.Note)
		f.CreatedAt = ca.Format("2006-01-02 15:04:05")
		detail.Followups = append(detail.Followups, f)
	}

	return detail, nil
}

func (r *EventRepo) CreateEventTx(name, color, note string, devices []string, iocs []IOC) (int, error) {
	tx, err := r.DB.Begin()
	if err != nil {
		return 0, err
	}

	var id int
	err = tx.QueryRow(
		"INSERT INTO mined_events (event_name, color, status, mined_at, note) VALUES ($1, $2, 'active', $3, $4) RETURNING id",
		name, color, time.Now(), note,
	).Scan(&id)
	if err != nil {
		tx.Rollback()
		return 0, err
	}

	for _, d := range devices {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		if _, err := tx.Exec(
			"INSERT INTO mined_event_devices (event_id, device_id) VALUES ($1, UPPER($2)) ON CONFLICT DO NOTHING",
			id, d,
		); err != nil {
			tx.Rollback()
			return 0, err
		}
	}

	for _, ioc := range iocs {
		if _, err := tx.Exec(
			"INSERT INTO mined_event_iocs (event_id, target, port) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
			id, ioc.Target, ioc.Port,
		); err != nil {
			tx.Rollback()
			return 0, err
		}
	}

	if err := tx.Commit(); err != nil {
		return 0, err
	}
	return id, nil
}

func (r *EventRepo) UpdateEvent(id int, name, color, status, note string) error {
	_, err := r.DB.Exec(
		"UPDATE mined_events SET event_name = $1, color = $2, status = $3, note = $4 WHERE id = $5",
		name, color, status, note, id,
	)
	return err
}

func (r *EventRepo) DeleteEvent(id int) error {
	_, err := r.DB.Exec("DELETE FROM mined_events WHERE id = $1", id)
	return err
}

func (r *EventRepo) AddFollowup(eventID int, actionType, note string) error {
	_, err := r.DB.Exec(
		"INSERT INTO event_followups (event_id, action_type, created_at, note) VALUES ($1, $2, $3, $4)",
		eventID, actionType, time.Now(), note,
	)
	return err
}

func (r *EventRepo) AddDevices(eventID int, devices []string) error {
	for _, d := range devices {
		d = strings.TrimSpace(d)
		if d == "" {
			continue
		}
		if _, err := r.DB.Exec(
			"INSERT INTO mined_event_devices (event_id, device_id) VALUES ($1, UPPER($2)) ON CONFLICT DO NOTHING",
			eventID, d,
		); err != nil {
			return err
		}
	}
	return nil
}

func (r *EventRepo) AddIOCs(eventID int, iocs []IOC) error {
	for _, ioc := range iocs {
		if _, err := r.DB.Exec(
			"INSERT INTO mined_event_iocs (event_id, target, port) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
			eventID, ioc.Target, ioc.Port,
		); err != nil {
			return err
		}
	}
	return nil
}

func (r *EventRepo) RemoveDevice(eventID int, deviceID string) error {
	_, err := r.DB.Exec(
		"DELETE FROM mined_event_devices WHERE event_id = $1 AND device_id = UPPER($2)",
		eventID, deviceID,
	)
	return err
}

func (r *EventRepo) RemoveIOCs(eventID int, target, port string) error {
	_, err := r.DB.Exec(
		"DELETE FROM mined_event_iocs WHERE event_id = $1 AND target = $2 AND COALESCE(port, '') = $3",
		eventID, target, port,
	)
	return err
}
