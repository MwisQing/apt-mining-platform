# v4.19 功能补全实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 3 个独立页面（告警标注、审计日志、设备管理），完善后端 API 和前端导航。

**Architecture:** 后端新增 2 个 Go 文件（audit_handler.go, audit_repo.go）+ 增强 1 个现有文件（device_repo.go）；前端新增 3 个 Vue 页面 + 2 个 API 封装文件 + 路由 + 侧边栏。

**Tech Stack:** Go 1.22 + Gin + PostgreSQL（后端） / Vue 3 + Element Plus（前端）

---

## 文件映射

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `backend_v2/internal/handler/audit_handler.go` | 审计日志 HTTP handler |
| 新建 | `backend_v2/internal/repository/audit_repo.go` | 审计日志数据库层 |
| 修改 | `backend_v2/main.go:59-77` | 注册 audit handler + 路由 |
| 修改 | `backend_v2/internal/repository/device_repo.go` | 增强 DeviceItem + 新增标签绑定方法 |
| 修改 | `backend_v2/internal/handler/device_handler.go` | 新增标签绑定/解绑接口 |
| 新建 | `frontend/src/views/AlertAnnotation.vue` | 告警标注页面 |
| 新建 | `frontend/src/views/AuditLog.vue` | 审计日志页面 |
| 新建 | `frontend/src/views/DeviceManager.vue` | 设备管理页面 |
| 新建 | `frontend/src/api/audit.js` | 审计日志 API 封装 |
| 新建 | `frontend/src/api/devices.js` | 设备管理 API 封装 |
| 修改 | `frontend/src/router/index.js` | 新增 3 条路由 |
| 修改 | `frontend/src/App.vue` | 侧边栏新增 3 个导航项 |

---

### Task 1: 审计日志后端 — audit_repo.go

**Files:**
- Create: `backend_v2/internal/repository/audit_repo.go`

**责任**：读 `audit_log` 表，支持分页 + 时间范围 + 操作类型过滤 + 关键词搜索

```go
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

	// Count
	var total int64
	countSQL := fmt.Sprintf("SELECT COUNT(*) FROM audit_log %s", where)
	if err := r.DB.QueryRow(countSQL, args...).Scan(&total); err != nil {
		return nil, 0, err
	}

	// Query
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
		rows.Scan(&item.ID, &item.Action, &item.TargetType, &item.TargetID, &item.Detail, &item.CreatedAt)
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
		rows.Scan(&a)
		actions = append(actions, a)
	}
	return actions, nil
}
```

**验证**：`cd backend_v2 && go build ./...` 无报错

---

### Task 2: 审计日志后端 — audit_handler.go

**Files:**
- Create: `backend_v2/internal/handler/audit_handler.go`

**责任**：`GET /api/audit-log` HTTP handler，解析查询参数 → 调 repo → 返回分页 JSON

```go
package handler

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"apt-mining-platform/v2/internal/repository"
)

type AuditHandler struct {
	Repo *repository.AuditRepo
}

func NewAuditHandler(repo *repository.AuditRepo) *AuditHandler {
	return &AuditHandler{Repo: repo}
}

// GetAuditLogs GET /api/audit-log
func (h *AuditHandler) GetAuditLogs(c *gin.Context) {
	p := &repository.AuditQueryParams{
		DateStart: c.Query("date_start"),
		DateEnd:   c.Query("date_end"),
		Action:    c.Query("action_type"),
		Keyword:   c.Query("keyword"),
		Page:      parseInt(c.Query("page"), 1),
		PageSize:  parseInt(c.Query("page_size"), 50),
	}

	items, total, err := h.Repo.QueryLogs(p)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"items":     items,
		"total":     total,
		"page":      p.Page,
		"page_size": p.PageSize,
	})
}

// GetAuditActions GET /api/audit-log/actions — 操作类型选项
func (h *AuditHandler) GetAuditActions(c *gin.Context) {
	actions, err := h.Repo.GetActionOptions()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"actions": actions})
}
```

**验证**：`cd backend_v2 && go build ./...` 无报错

---

### Task 3: 注册审计日志路由

**Files:**
- Modify: `backend_v2/main.go`

在现有 handler 初始化区域（第 76 行之后）新增：

```go
	auditRepo := repository.NewAuditRepo(database)
	auditHandler := handler.NewAuditHandler(auditRepo)
```

在 `api` 路由组内（第 143 行 `api.GET("/persistence", ...)` 之前）新增：

```go
		api.GET("/audit-log", auditHandler.GetAuditLogs)
		api.GET("/audit-log/actions", auditHandler.GetAuditActions)
```

**验证**：`cd backend_v2 && go build ./...` 无报错

---

### Task 4: 设备管理后端增强 — device_repo.go

**Files:**
- Modify: `backend_v2/internal/repository/device_repo.go`

**4.1 增强 DeviceItem 结构体**（替换第 13-18 行）

```go
type DeviceItem struct {
	DeviceID      string   `json:"device_id"`
	AlertCount    int      `json:"alert_count"`
	FirstSeen     string   `json:"first_seen"`
	LastSeen      string   `json:"last_seen"`
	DeviceTags    []string `json:"device_tags"`
	EventCount    int      `json:"event_count"`
	DeviceNote    string   `json:"device_note"`
}
```

**4.2 新增 AddDeviceTags 方法**（追加到文件末尾）

```go
func (r *DeviceRepo) AddDeviceTags(deviceID string, tagNames []string) error {
	for _, tagName := range tagNames {
		tagName = strings.TrimSpace(tagName)
		if tagName == "" {
			continue
		}
		// 查找或创建标签
		var tagID int
		err := r.DB.QueryRow("SELECT id FROM tags WHERE name = $1", tagName).Scan(&tagID)
		if err == sql.ErrNoRows {
			// 创建新标签
			result, err := r.DB.Exec(
				"INSERT INTO tags (name, color, is_permanent, created_at) VALUES ($1, $2, 0, NOW())",
				tagName, "#409EFF")
			if err != nil {
				return err
			}
			tagID64, _ := result.LastInsertId()
			tagID = int(tagID64)
		} else if err != nil {
			return err
		}
		// 插入设备标签（忽略重复）
		_, err = r.DB.Exec(
			"INSERT INTO device_tags (device_id, tag_id, created_at) VALUES ($1, $2, NOW()) ON CONFLICT DO NOTHING",
			deviceID, tagID)
		if err != nil {
			return err
		}
	}
	return nil
}
```

需要 import `"strings"` 和 `"database/sql"`（已存在）。

**4.3 新增 RemoveDeviceTag 方法**（追加到文件末尾）

```go
func (r *DeviceRepo) RemoveDeviceTag(deviceID, tagName string) error {
	_, err := r.DB.Exec(`
		DELETE FROM device_tags dt USING tags t
		WHERE dt.tag_id = t.id AND dt.device_id = $1 AND t.name = $2`,
		deviceID, tagName)
	return err
}
```

**4.4 增强 queryDevices 以返回标签和事件数**（修改 `queryDevices` 方法，第 110-127 行）

```go
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
```

**4.5 增强 4 个查询方法的 SQL**（在 `GROUP BY a.device_id` 之后增加子查询）

修改 `queryByTagAndKeyword`（第 34-43 行）：

```sql
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
```

同样修改 `queryByTag`、`queryByKeyword`、`queryAll` 三个方法的 SELECT 语句，增加相同的两个子查询字段。

---

### Task 5: 设备管理后端 — 标签绑定 handler

**Files:**
- Modify: `backend_v2/internal/handler/device_handler.go`

追加到文件末尾：

```go
import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"apt-mining-platform/v2/internal/repository"
)

// AddDeviceTags POST /api/devices/:id/tags
func (h *DeviceHandler) AddDeviceTags(c *gin.Context) {
	deviceID := c.Param("id")
	var req struct {
		Tags []string `json:"tags"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	if err := h.Repo.AddDeviceTags(deviceID, req.Tags); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// RemoveDeviceTag DELETE /api/devices/:id/tags/:tag_name
func (h *DeviceHandler) RemoveDeviceTag(c *gin.Context) {
	deviceID := c.Param("id")
	tagName := c.Param("tag_name")
	if err := h.Repo.RemoveDeviceTag(deviceID, tagName); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}
```

**验证**：`cd backend_v2 && go build ./...` 无报错

---

### Task 6: 注册设备管理路由

**Files:**
- Modify: `backend_v2/main.go`

将第 134 行 `api.GET("/devices", deviceHandler.ListDevices)` 替换为：

```go
		api.GET("/devices", deviceHandler.ListDevices)
		api.POST("/devices/:id/tags", deviceHandler.AddDeviceTags)
		api.DELETE("/devices/:id/tags/:tag_name", deviceHandler.RemoveDeviceTag)
```

**验证**：`cd backend_v2 && go build ./...` 无报错

---

### Task 7: 告警标注页前端 — AlertAnnotation.vue

**Files:**
- Create: `frontend/src/views/AlertAnnotation.vue`

```vue
<template>
  <div class="annotation-page">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">告警标注</span>
        <h2 class="page-banner__title">人工标注</h2>
        <p class="page-banner__desc">对单条告警设置分析状态、重点关注状态和备注。</p>
      </div>
    </section>

    <section class="filter-bar">
      <div class="filter-bar__intro">
        <div>
          <div class="filter-bar__title">告警筛选</div>
          <div class="filter-bar__hint">按日期、威胁类型和关键词筛选。</div>
        </div>
        <el-button size="small" @click="loadData">
          <el-icon><RefreshRight /></el-icon>
          刷新
        </el-button>
      </div>

      <div class="filter-row">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          size="small"
          class="filter-item"
        />

        <el-select
          v-model="threatType"
          placeholder="威胁类型"
          size="small"
          clearable
          class="filter-item"
          @change="loadData"
        >
          <el-option v-for="opt in threatTypes" :key="opt" :label="opt" :value="opt" />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="关键字搜索"
          size="small"
          clearable
          class="filter-item"
          @keyup.enter="loadData"
          @clear="loadData"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>

        <el-button type="primary" size="small" @click="loadData">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </div>
    </section>

    <section class="table-card">
      <el-table :data="tableData" size="small" v-loading="loading" stripe row-key="id">
        <el-table-column label="ID" width="60">
          <template #default="{ row }">{{ row.id }}</template>
        </el-table-column>

        <el-table-column label="设备ID" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_id }}</template>
        </el-table-column>

        <el-table-column label="源IP" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.source_ip || '-' }}</template>
        </el-table-column>

        <el-table-column label="外联目标" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target }}</template>
        </el-table-column>

        <el-table-column label="威胁类型" width="100">
          <template #default="{ row }">
            <el-tag :type="threatTypeTag(row.threat_type)" size="small">{{ row.threat_type || '-' }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="威胁等级" width="80" align="center">
          <template #default="{ row }">{{ row.threat_level || '-' }}</template>
        </el-table-column>

        <el-table-column label="分析状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="analysisStatusType(row.analysis_status)" size="small">
              {{ row.analysis_status || '未分析' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="重点关注" width="80" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.is_focused" color="#F56C6C" :size="16"><StarFilled /></el-icon>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>

        <el-table-column label="首次告警" width="165">
          <template #default="{ row }">{{ row.first_alert_time || '-' }}</template>
        </el-table-column>

        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="openAnnotate(row)">标注</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[50, 100, 200, 500]"
          layout="total, sizes, prev, pager, next"
          background
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </section>

    <el-dialog v-model="dialogVisible" title="告警标注" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="分析状态">
          <el-select v-model="form.analysis_status" placeholder="选择分析状态" style="width: 100%">
            <el-option label="未分析" value="" />
            <el-option label="分析中" value="分析中" />
            <el-option label="已完成" value="已完成" />
          </el-select>
        </el-form-item>
        <el-form-item label="重点关注">
          <el-switch v-model="form.is_focused" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAnnotation" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RefreshRight, Search, StarFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { annotateAlert, fetchAlerts, fetchAlertOptions } from '../api/alerts'

const threatTypes = ref([])
const dateRange = ref(null)
const threatType = ref('')
const keyword = ref('')

const tableData = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)

const dialogVisible = ref(false)
const saving = ref(false)
const form = ref({ id: null, analysis_status: '', is_focused: false })

async function loadOptions() {
  try {
    const res = await fetchAlertOptions()
    threatTypes.value = res.threat_types || []
  } catch { /* ignore */ }
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    if (dateRange.value?.length === 2) {
      params.date_start = dateRange.value[0]
      params.date_end = dateRange.value[1]
    }
    if (threatType.value) params.threat_types = threatType.value
    if (keyword.value) params.keyword = keyword.value

    const res = await fetchAlerts(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error(`加载告警失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

function openAnnotate(row) {
  form.value = { id: row.id, analysis_status: row.analysis_status || '', is_focused: !!row.is_focused }
  dialogVisible.value = true
}

async function saveAnnotation() {
  saving.value = true
  try {
    await annotateAlert(form.value.id, {
      analysis_status: form.value.analysis_status,
      is_focused: form.value.is_focused,
    })
    ElMessage.success('标注已保存')
    dialogVisible.value = false
    loadData()
  } catch (e) {
    ElMessage.error(`保存失败: ${e.message}`)
  } finally {
    saving.value = false
  }
}

function threatTypeTag(type) {
  if (!type) return 'info'
  const lower = type.toLowerCase()
  if (lower.includes('apt')) return 'danger'
  if (lower.includes('远控') || lower.includes('remote')) return 'warning'
  return 'info'
}

function analysisStatusType(status) {
  if (!status || status === '') return 'info'
  if (status === '分析中') return 'warning'
  if (status === '已完成') return 'success'
  return 'info'
}

onMounted(() => { loadOptions(); loadData() })
</script>

<style scoped>
.annotation-page { display: flex; flex-direction: column; gap: 18px; }
.page-banner { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 16px 0; }
.page-banner__eyebrow { color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
.page-banner__title { margin: 4px 0 0; font-size: 22px; font-weight: 700; }
.page-banner__desc { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.filter-bar { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.filter-bar__intro { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 12px; }
.filter-bar__title { font-size: 13px; font-weight: 600; }
.filter-bar__hint { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { min-width: 140px; }
.table-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.pagination-bar { display: flex; justify-content: center; margin-top: 16px; }
.empty-cell { color: var(--text-muted); }
</style>
```

---

### Task 8: 审计日志 API 封装 + 设备管理 API 封装

**Files:**
- Create: `frontend/src/api/audit.js`

```javascript
import api from './index'

export function fetchAuditLogs(params) {
  return api.get('/api/audit-log', { params })
}

export function fetchAuditActions() {
  return api.get('/api/audit-log/actions')
}
```

**Files:**
- Create: `frontend/src/api/devices.js`

```javascript
import api from './index'

export function listDevices(params) {
  return api.get('/api/devices', { params })
}

export function addDeviceTags(deviceId, tags) {
  return api.post(`/api/devices/${deviceId}/tags`, { tags })
}

export function removeDeviceTag(deviceId, tagName) {
  return api.delete(`/api/devices/${deviceId}/tags/${encodeURIComponent(tagName)}`)
}
```

---

### Task 9: 审计日志页前端 — AuditLog.vue

**Files:**
- Create: `frontend/src/views/AuditLog.vue`

```vue
<template>
  <div class="audit-page">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">审计日志</span>
        <h2 class="page-banner__title">操作记录</h2>
        <p class="page-banner__desc">查看系统操作历史：谁在何时做了什么。</p>
      </div>
    </section>

    <section class="filter-bar">
      <div class="filter-row">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          size="small"
          class="filter-item"
        />

        <el-select
          v-model="actionType"
          placeholder="操作类型"
          size="small"
          clearable
          class="filter-item"
          @change="loadData"
        >
          <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="关键词搜索"
          size="small"
          clearable
          class="filter-item"
          @keyup.enter="loadData"
          @clear="loadData"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>

        <el-button type="primary" size="small" @click="loadData">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </div>
    </section>

    <section class="table-card">
      <el-table :data="tableData" size="small" v-loading="loading" stripe row-key="id">
        <el-table-column label="时间" width="165">
          <template #default="{ row }">{{ row.created_at }}</template>
        </el-table-column>

        <el-table-column label="操作类型" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.action }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="目标类型" width="100">
          <template #default="{ row }">{{ row.target_type || '-' }}</template>
        </el-table-column>

        <el-table-column label="目标ID" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_id || '-' }}</template>
        </el-table-column>

        <el-table-column label="详情" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.detail || '-' }}</template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[50, 100, 200]"
          layout="total, sizes, prev, pager, next"
          background
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fetchAuditActions, fetchAuditLogs } from '../api/audit'

const dateRange = ref(null)
const actionType = ref('')
const keyword = ref('')
const actions = ref([])

const tableData = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)

async function loadActions() {
  try {
    const res = await fetchAuditActions()
    actions.value = res.actions || []
  } catch { /* ignore */ }
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    if (dateRange.value?.length === 2) {
      params.date_start = dateRange.value[0]
      params.date_end = dateRange.value[1]
    }
    if (actionType.value) params.action_type = actionType.value
    if (keyword.value) params.keyword = keyword.value

    const res = await fetchAuditLogs(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error(`加载日志失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => { loadActions(); loadData() })
</script>

<style scoped>
.audit-page { display: flex; flex-direction: column; gap: 18px; }
.page-banner { display: flex; align-items: flex-start; gap: 16px; padding: 16px 0; }
.page-banner__eyebrow { color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
.page-banner__title { margin: 4px 0 0; font-size: 22px; font-weight: 700; }
.page-banner__desc { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.filter-bar { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { min-width: 140px; }
.table-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.pagination-bar { display: flex; justify-content: center; margin-top: 16px; }
</style>
```

---

### Task 10: 设备管理页前端 — DeviceManager.vue

**Files:**
- Create: `frontend/src/views/DeviceManager.vue`

```vue
<template>
  <div class="device-page">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">设备管理</span>
        <h2 class="page-banner__title">设备列表</h2>
        <p class="page-banner__desc">按设备维度查看标签、事件关联和告警统计。</p>
      </div>
    </section>

    <section class="filter-bar">
      <div class="filter-row">
        <el-input
          v-model="keyword"
          placeholder="搜索设备ID"
          size="small"
          clearable
          class="filter-item"
          @keyup.enter="loadData"
          @clear="loadData"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>

        <el-select
          v-model="tagFilter"
          placeholder="标签筛选"
          size="small"
          clearable
          multiple
          collapse-tags
          class="filter-item"
          @change="loadData"
        >
          <el-option v-for="t in allTags" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>

        <el-button type="primary" size="small" @click="loadData">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </div>
    </section>

    <section class="table-card">
      <el-table :data="tableData" size="small" v-loading="loading" stripe row-key="device_id">
        <el-table-column label="设备ID" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="device-id" @click="copyDeviceId(row.device_id)" title="点击复制">{{ row.device_id }}</span>
          </template>
        </el-table-column>

        <el-table-column label="标签" min-width="180">
          <template #default="{ row }">
            <div class="tag-chips">
              <el-tag v-for="tag in row.device_tags" :key="tag" size="small" class="tag-chip">{{ tag }}</el-tag>
              <span v-if="!row.device_tags.length" class="empty-cell">-</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="告警数" width="80" align="center">
          <template #default="{ row }">{{ row.alert_count }}</template>
        </el-table-column>

        <el-table-column label="事件数" width="80" align="center">
          <template #default="{ row }">{{ row.event_count }}</template>
        </el-table-column>

        <el-table-column label="最后活跃" width="165">
          <template #default="{ row }">{{ row.last_seen || '-' }}</template>
        </el-table-column>

        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openTagEditor(row)">编辑标签</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[50, 100, 200]"
          layout="total, sizes, prev, pager, next"
          background
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </section>

    <el-dialog v-model="tagDialogVisible" :title="'编辑标签: ' + editingDevice.device_id" width="420px">
      <div class="tag-editor">
        <div class="tag-editor__current">
          <div class="tag-editor__label">当前标签：</div>
          <div class="tag-editor__tags">
            <el-tag v-for="tag in currentTags" :key="tag" size="small" closable @close="removeTag(tag)">{{ tag }}</el-tag>
            <span v-if="!currentTags.length" class="empty-cell">无</span>
          </div>
        </div>
        <div class="tag-editor__add">
          <el-select v-model="newTag" placeholder="选择或输入标签" filterable allow-create style="width: 100%">
            <el-option v-for="t in allTags" :key="t.name" :label="t.name" :value="t.name" />
          </el-select>
          <el-button type="primary" size="small" @click="addTag" style="margin-top: 8px">添加</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="tagDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { listDevices, addDeviceTags, removeDeviceTag } from '../api/devices'
import { fetchTags } from '../api/tags'

const keyword = ref('')
const tagFilter = ref([])
const allTags = ref([])

const tableData = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)

const tagDialogVisible = ref(false)
const editingDevice = ref({ device_id: '' })
const currentTags = ref([])
const newTag = ref('')

async function loadAllTags() {
  try {
    allTags.value = await fetchTags()
  } catch { /* ignore */ }
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (tagFilter.value.length > 0) params.tags = tagFilter.value.join(',')

    const res = await listDevices(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error(`加载设备列表失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

function openTagEditor(row) {
  editingDevice.value = { device_id: row.device_id }
  currentTags.value = [...(row.device_tags || [])]
  newTag.value = ''
  tagDialogVisible.value = true
}

async function addTag() {
  if (!newTag.value) return
  try {
    await addDeviceTags(editingDevice.value.device_id, [newTag.value])
    ElMessage.success('标签已添加')
    currentTags.value.push(newTag.value)
    newTag.value = ''
    loadData()
  } catch (e) {
    ElMessage.error(`添加失败: ${e.message}`)
  }
}

async function removeTag(tagName) {
  try {
    await removeDeviceTag(editingDevice.value.device_id, tagName)
    ElMessage.success('标签已移除')
    currentTags.value = currentTags.value.filter(t => t !== tagName)
    loadData()
  } catch (e) {
    ElMessage.error(`移除失败: ${e.message}`)
  }
}

function copyDeviceId(id) {
  navigator.clipboard.writeText(id)
  ElMessage.success('已复制: ' + id)
}

onMounted(() => { loadAllTags(); loadData() })
</script>

<style scoped>
.device-page { display: flex; flex-direction: column; gap: 18px; }
.page-banner { display: flex; align-items: flex-start; gap: 16px; padding: 16px 0; }
.page-banner__eyebrow { color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
.page-banner__title { margin: 4px 0 0; font-size: 22px; font-weight: 700; }
.page-banner__desc { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.filter-bar { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { min-width: 140px; }
.table-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.pagination-bar { display: flex; justify-content: center; margin-top: 16px; }
.empty-cell { color: var(--text-muted); }
.device-id { cursor: pointer; color: var(--accent); }
.device-id:hover { text-decoration: underline; }
.tag-chips { display: flex; gap: 4px; flex-wrap: wrap; }
.tag-chip { margin: 0; }
.tag-editor { display: flex; flex-direction: column; gap: 16px; }
.tag-editor__label { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.tag-editor__tags { display: flex; gap: 4px; flex-wrap: wrap; min-height: 28px; }
.tag-editor__add { display: flex; flex-direction: column; }
</style>
```

---

### Task 11: 注册前端路由

**Files:**
- Modify: `frontend/src/router/index.js`

替换整个文件内容为：

```javascript
import { createRouter, createWebHistory } from 'vue-router'
import Workbench from '../views/Workbench.vue'
import AlertList from '../views/AlertList.vue'
import AlertAnnotation from '../views/AlertAnnotation.vue'
import EventManager from '../views/EventManager.vue'
import DeviceManager from '../views/DeviceManager.vue'
import IocNotes from '../views/IocNotes.vue'
import Settings from '../views/Settings.vue'
import AuditLog from '../views/AuditLog.vue'

const routes = [
  { path: '/', component: Workbench, meta: { title: '研判工作台' } },
  { path: '/alerts', component: AlertList, meta: { title: '原始告警' } },
  { path: '/annotations', component: AlertAnnotation, meta: { title: '告警标注' } },
  { path: '/events', component: EventManager, meta: { title: '事件管理' } },
  { path: '/devices', component: DeviceManager, meta: { title: '设备管理' } },
  { path: '/ioc-notes', component: IocNotes, meta: { title: 'IOC 备注' } },
  { path: '/settings', component: Settings, meta: { title: '导入与设置' } },
  { path: '/audit', component: AuditLog, meta: { title: '审计日志' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} - APT Mining Workbench` : 'APT Mining Workbench'
})

export default router
```

---

### Task 12: 侧边栏新增导航项

**Files:**
- Modify: `frontend/src/App.vue`

**12.1 新增 import 图标**（第 90-98 行，替换）

```javascript
import {
  ArrowLeft,
  ArrowRight,
  Connection,
  Document,
  EditPen,
  FolderOpened,
  List,
  Monitor,
  Notebook,
  Setting,
} from '@element-plus/icons-vue'
```

**12.2 更新 navItems**（第 110-116 行，替换）

```javascript
const navItems = [
  { path: '/', label: '研判工作台', icon: Monitor },
  { path: '/alerts', label: '原始告警', icon: List },
  { path: '/annotations', label: '告警标注', icon: EditPen },
  { path: '/events', label: '事件管理', icon: FolderOpened },
  { path: '/devices', label: '设备管理', icon: Connection },
  { path: '/ioc-notes', label: 'IOC 备注', icon: Notebook },
  { path: '/settings', label: '导入与设置', icon: Setting },
  { path: '/audit', label: '审计日志', icon: Document },
]
```

**12.3 新增 pageMeta**（第 118-144 行，在现有 entries 基础上追加）

```javascript
  '/annotations': {
    kicker: '',
    title: '告警标注',
    subtitle: '对单条告警设置分析状态和重点关注，沉淀人工判断。',
  },
  '/devices': {
    kicker: '',
    title: '设备管理',
    subtitle: '按设备维度查看标签、关联事件和告警统计。',
  },
  '/audit': {
    kicker: '',
    title: '审计日志',
    subtitle: '查看系统操作历史记录，追踪每一步变更。',
  },
```

**12.4 更新 TOPBAR_HIDDEN_ROUTES**（第 153 行，追加 3 个新路由）

```javascript
const TOPBAR_HIDDEN_ROUTES = new Set(['/events', '/ioc-notes', '/settings', '/alerts', '/annotations', '/devices', '/audit'])
```

---

### Task 13: 构建 + 同步静态文件

```bash
cd frontend && npm run build
```

同步到后端静态目录：

```powershell
Remove-Item -Recurse -Force backend_v2\static\assets\* -ErrorAction SilentlyContinue
Copy-Item -Force frontend\dist\* backend_v2\static\ -Recurse
```

---

### Task 14: 启动验证 + 回归测试

1. 启动后端：`python dev.py` 或 `cd backend_v2 && apt-mining.exe`
2. 验证 3 个新页面可访问：
   - `http://127.0.0.1:9099/annotations` — 加载告警列表，标注弹窗可用
   - `http://127.0.0.1:9099/audit` — 加载审计日志（可能有数据或空表）
   - `http://127.0.0.1:9099/devices` — 加载设备列表，编辑标签可用
3. 验证侧边栏 8 个导航项均可点击跳转
4. 运行回归测试：`python scripts/test_api.py`（如果存在）

---

## 自审查

### Spec 覆盖检查

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 告警标注页 `/annotations` | Task 7, 11, 12 |
| 审计日志后端 `GET /api/audit-log` | Task 1, 2, 3 |
| 审计日志页 `/audit` | Task 8, 9, 11, 12 |
| 设备管理后端增强（JOIN + 标签绑定/解绑） | Task 4, 5, 6 |
| 设备管理页 `/devices` | Task 8, 10, 11, 12 |
| 侧边栏 3 个新条目 | Task 12 |
| 文件 ≤ 400 行 | 每个新 Vue 文件约 150-200 行，每个 Go 文件约 80-120 行 |
| 不改现有页面逻辑 | 仅新增文件 + 修改路由/侧边栏 |
| 审计日志只读 | 仅 GET 接口，无编辑/删除 |

### 占位符扫描
无 "TBD"、"TODO"、"implement later"、"add validation" 等占位符。

### 类型一致性
- `AuditLogItem` 在 Task 1 定义，Task 2 handler 直接使用，Task 9 前端消费字段名一致
- `DeviceItem` 在 Task 4 增强，Task 5 handler 复用，Task 10 前端消费字段名一致
- API 路径 `POST /api/devices/:id/tags` 与 Task 6 注册、Task 8 封装、Task 10 调用一致

### 无遗漏
所有 spec 要求均有对应 task 实现。
