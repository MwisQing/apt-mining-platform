package repository

import (
	"database/sql"
	"fmt"
)

type AuditRepo struct {
	DB *sql.DB
}

func NewAuditRepo(db *sql.DB) *AuditRepo { return &AuditRepo{DB: db} }

type AuditLogItem struct {
	ID         int    `json:"id"`
	Action     string `json:"action"`
	TargetType string `json:"target_type"`
	TargetID   string `json:"target_id"`
	Detail     string `json:"detail"`
	CreatedAt  string `json:"created_at"`
}

type AuditQueryParams struct {
	DateStart string
	DateEnd   string
	Action    string
	Keyword   string
	Page      int
	PageSize  int
}

func (r *AuditRepo) QueryLogs(p *AuditQueryParams) ([]AuditLogItem, int64, error) {
	conditions := []string{}
	args := []interface{}{}
	argIdx := 1

	if p.DateStart != "" {
		conditions = append(conditions, fmt.Sprintf("created_at >= $%d", argIdx))
		args = append(args, p.DateStart+" 00:00:00")
		argIdx++
	}
	if p.DateEnd != "" {
		conditions = append(conditions, fmt.Sprintf("created_at < ($%d::date + interval '1 day')", argIdx))
		args = append(args, p.DateEnd)
		argIdx++
	}
	if p.Action != "" {
		conditions = append(conditions, fmt.Sprintf("action = $%d", argIdx))
		args = append(args, p.Action)
		argIdx++
	}
	if p.Keyword != "" {
		conditions = append(conditions, fmt.Sprintf("(target_id ILIKE $%d OR detail ILIKE $%d)", argIdx, argIdx))
		args = append(args, "%"+p.Keyword+"%")
		argIdx++
	}

	where := ""
	if len(conditions) > 0 {
		where = "WHERE " + joinConditions(conditions)
	}

	var total int64
	countSQL := fmt.Sprintf("SELECT COUNT(*) FROM audit_log %s", where)
	if err := r.DB.QueryRow(countSQL, args...).Scan(&total); err != nil {
		return nil, 0, err
	}

	querySQL := fmt.Sprintf(`
		SELECT id, action, target_type, target_id, detail,
		       to_char(created_at, 'YYYY-MM-DD HH24:MI:SS')
		FROM audit_log %s ORDER BY created_at DESC LIMIT $%d OFFSET $%d`,
		where, argIdx, argIdx+1)
	args = append(args, p.PageSize, (p.Page-1)*p.PageSize)

	rows, err := r.DB.Query(querySQL, args...)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()

	var items []AuditLogItem
	for rows.Next() {
		var item AuditLogItem
		if err := rows.Scan(&item.ID, &item.Action, &item.TargetType, &item.TargetID, &item.Detail, &item.CreatedAt); err != nil {
			return nil, 0, err
		}
		items = append(items, item)
	}
	if items == nil {
		items = []AuditLogItem{}
	}
	return items, total, nil
}

func joinConditions(conditions []string) string {
	result := conditions[0]
	for i := 1; i < len(conditions); i++ {
		result += " AND " + conditions[i]
	}
	return result
}

func (r *AuditRepo) GetActionOptions() ([]string, error) {
	rows, err := r.DB.Query("SELECT DISTINCT action FROM audit_log ORDER BY action")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var actions []string
	for rows.Next() {
		var a string
		if err := rows.Scan(&a); err != nil {
			return nil, err
		}
		actions = append(actions, a)
	}
	return actions, nil
}
