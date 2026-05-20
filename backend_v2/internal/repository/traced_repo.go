package repository

import (
	"database/sql"
	"time"
)

type TracedRepo struct {
	DB *sql.DB
}

func NewTracedRepo(db *sql.DB) *TracedRepo { return &TracedRepo{DB: db} }

type TracedItem struct {
	ID       int    `json:"id"`
	Target   string `json:"target"`
	Port     string `json:"port"`
	TracedAt string `json:"traced_at"`
	Note     string `json:"note"`
}

func (r *TracedRepo) List(keyword string) ([]TracedItem, error) {
	query := "SELECT id, target, port, to_char(traced_at, 'YYYY-MM-DD HH24:MI:SS'), note FROM traced_targets"
	args := []interface{}{}
	if keyword != "" {
		query += " WHERE target LIKE $1"
		args = append(args, "%"+keyword+"%")
	}
	query += " ORDER BY traced_at DESC"

	rows, err := r.DB.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var items []TracedItem
	for rows.Next() {
		var it TracedItem
		rows.Scan(&it.ID, &it.Target, &it.Port, &it.TracedAt, &it.Note)
		items = append(items, it)
	}
	if items == nil {
		items = []TracedItem{}
	}
	return items, nil
}

func (r *TracedRepo) Create(target, port, note string) error {
	_, err := r.DB.Exec(
		"INSERT INTO traced_targets (target, port, traced_at, note) VALUES ($1, $2, $3, $4) ON CONFLICT (target, port) DO UPDATE SET note = EXCLUDED.note, traced_at = $3",
		target, port, time.Now(), note,
	)
	return err
}

func (r *TracedRepo) Update(id int, target, port, note string) error {
	_, err := r.DB.Exec(
		"UPDATE traced_targets SET target = $1, port = $2, note = $3 WHERE id = $4",
		target, port, note, id,
	)
	return err
}

func (r *TracedRepo) Delete(id int) error {
	_, err := r.DB.Exec("DELETE FROM traced_targets WHERE id = $1", id)
	return err
}

func (r *TracedRepo) BatchCreate(items []TracedItem) (int, error) {
	count := 0
	for _, item := range items {
		_, err := r.DB.Exec(
			"INSERT INTO traced_targets (target, port, traced_at, note) VALUES ($1, $2, $3, $4) ON CONFLICT (target, port) DO NOTHING",
			item.Target, item.Port, time.Now(), item.Note,
		)
		if err == nil {
			count++
		}
	}
	return count, nil
}
