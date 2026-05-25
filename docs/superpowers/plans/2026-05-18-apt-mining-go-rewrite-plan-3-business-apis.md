# Plan 3: 事件、标签、追踪管理

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现事件管理（CRUD + IOC + 设备关联 + 跟进）、标签管理（批次 + 批量打标）、追踪库管理。

**Architecture:** 纯 CRUD 操作，每个 API 对应 handler → service → repo 三层。IOC 提取逻辑复用 Python 版的正则规则。所有写操作后不需要同步快照（已删除快照表）。

**Tech Stack:** Go `database/sql`, lib/pq, regex

**依赖：** Plan 2 已完成（基础框架 + 核心查询引擎）。

---

### 任务概览

| 任务 | 产出 | 预计时间 |
|---|---|---|
| Task 1: IOC 提取 | `internal/service/ioc_extractor.go` | 10 min |
| Task 2: 事件 CRUD | handler + service + repo | 15 min |
| Task 3: 事件关联 | IOC 关联 + 设备关联 + 跟进 | 10 min |
| Task 4: 标签管理 | handler + service + repo | 10 min |
| Task 5: 批量打标 | TXT 导入 + 批次恢复 | 10 min |
| Task 6: 追踪管理 | handler + service + repo | 5 min |
| Task 7: 设备列表 | `GET /api/devices` | 5 min |

---

### Task 1: IOC 提取

**Files:**
- Create: `backend_v2/internal/service/ioc_extractor.go`

- [ ] **Step 1: 实现 IOC 提取（从 Python 版迁移）**

```go
package service

import (
    "regexp"
    "strings"
)

var (
    // IP 地址
    ipRegex = regexp.MustCompile(`\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b`)
    // 域名（含子域名）
    domainRegex = regexp.MustCompile(`\b([a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+\.[a-zA-Z]{2,})\b`)
    // MD5
    md5Regex = regexp.MustCompile(`\b([a-fA-F0-9]{32})\b`)
    // 设备ID（LAPTOP/SRV/PC/WIN 等前缀）
    deviceIDRegex = regexp.MustCompile(`\b((?:LAPTOP|SRV|PC|WIN|SERVER|DESKTOP|WS)[-_][A-Za-z0-9]+)\b`)
    // 端口跟随 IP
    ipPortRegex = regexp.MustCompile(`\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[:：](\d+)\b`)
    // URL
    urlRegex = regexp.MustCompile(`https?://[^\s<>"']{2,}`)
)

type IOCItem struct {
    Value string `json:"target"`
    Port  string `json:"port"`
    Type  string `json:"type"` // ip, domain, md5, device, url
}

// ExtractIOCs 从文本中提取 IOC
func ExtractIOCs(text string) []IOCItem {
    if text == "" {
        return nil
    }

    seen := make(map[string]bool)
    var results []IOCItem

    add := func(item IOCItem) {
        key := item.Value + ":" + item.Port
        if !seen[key] {
            seen[key] = true
            results = append(results, item)
        }
    }

    // IP:Port 优先提取
    for _, m := range ipPortRegex.FindAllStringSubmatch(text, -1) {
        ip := m[1]
        port := m[2]
        if isValidIP(ip) {
            add(IOCItem{Value: ip, Port: port, Type: "ip"})
        }
    }

    // 独立 IP
    for _, m := range ipRegex.FindAllStringSubmatch(text, -1) {
        ip := m[1]
        if isValidIP(ip) {
            // 检查是否已经被 IP:Port 覆盖
            key := ip + ":"
            already := false
            for _, r := range results {
                if r.Value == ip {
                    already = true
                    break
                }
            }
            if !already {
                add(IOCItem{Value: ip, Port: "", Type: "ip"})
            }
        }
    }

    // 域名
    for _, m := range domainRegex.FindAllStringSubmatch(text, -1) {
        domain := m[1]
        // 排除看起来不像 IOC 的常见域名
        if !isCommonDomain(domain) {
            add(IOCItem{Value: domain, Port: "", Type: "domain"})
        }
    }

    // MD5
    for _, m := range md5Regex.FindAllStringSubmatch(text, -1) {
        add(IOCItem{Value: m[1], Port: "", Type: "md5"})
    }

    // 设备ID
    for _, m := range deviceIDRegex.FindAllStringSubmatch(text, -1) {
        add(IOCItem{Value: strings.ToUpper(m[1]), Port: "", Type: "device"})
    }

    // URL
    for _, m := range urlRegex.FindAllString(text, -1) {
        add(IOCItem{Value: m, Port: "", Type: "url"})
    }

    return results
}

func isValidIP(ip string) bool {
    parts := strings.Split(ip, ".")
    if len(parts) != 4 {
        return false
    }
    for _, p := range parts {
        if len(p) == 0 || len(p) > 3 {
            return false
        }
        for _, c := range p {
            if c < '0' || c > '9' {
                return false
            }
        }
    }
    return true
}

func isCommonDomain(domain string) bool {
    commonSuffixes := []string{
        ".com.cn", ".cn", ".com", ".net", ".org",
        ".google.com", ".microsoft.com", ".amazon.com",
        ".apple.com", ".cloudflare.com",
    }
    lower := strings.ToLower(domain)
    // 排除明显的知名域名
    knownDomains := []string{
        "www.google.com", "www.baidu.com", "www.microsoft.com",
    }
    for _, kd := range knownDomains {
        if lower == kd {
            return true
        }
    }
    _ = commonSuffixes
    return false
}
```

---

### Task 2: 事件 CRUD

**Files:**
- Create: `backend_v2/internal/repository/event_repo.go`
- Create: `backend_v2/internal/service/event_service.go`
- Create: `backend_v2/internal/handler/event_handler.go`

- [ ] **Step 1: 创建 event_repo.go**

```go
package repository

import (
    "database/sql"
    "fmt"
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
    ID        int       `json:"id"`
    Name      string    `json:"event_name"`
    Color     string    `json:"color"`
    Status    string    `json:"status"`
    MinedAt   time.Time `json:"mined_at"`
    Note      string    `json:"note"`
}

type EventDetail struct {
    Event
    Devices   []string       `json:"devices"`
    IOCs      []EventIOC     `json:"iocs"`
    Followups []EventFollowup `json:"followups"`
}

type EventIOC struct {
    Target string `json:"target"`
    Port   string `json:"port"`
}

type EventFollowup struct {
    ID         int       `json:"id"`
    EventType  string    `json:"action_type"`
    CreatedAt  time.Time `json:"created_at"`
    Note       string    `json:"note"`
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
    err := r.DB.QueryRow(
        "SELECT id, event_name, color, status, mined_at, note FROM mined_events WHERE id = $1",
        id,
    ).Scan(&detail.ID, &detail.Name, &detail.Color, &detail.Status, &detail.MinedAt, &detail.Note)
    if err != nil {
        return nil, err
    }

    // 设备列表
    devRows, _ := r.DB.Query("SELECT device_id FROM mined_event_devices WHERE event_id = $1", id)
    defer devRows.Close()
    for devRows.Next() {
        var d string
        devRows.Scan(&d)
        detail.Devices = append(detail.Devices, d)
    }

    // IOC 列表
    iocRows, _ := r.DB.Query("SELECT target, port FROM mined_event_iocs WHERE event_id = $1", id)
    defer iocRows.Close()
    for iocRows.Next() {
        var ioc EventIOC
        iocRows.Scan(&ioc.Target, &ioc.Port)
        detail.IOCs = append(detail.IOCs, ioc)
    }

    // 跟进记录
    fRows, _ := r.DB.Query("SELECT id, action_type, created_at, note FROM event_followups WHERE event_id = $1 ORDER BY created_at ASC", id)
    defer fRows.Close()
    for fRows.Next() {
        var f EventFollowup
        fRows.Scan(&f.ID, &f.EventType, &f.CreatedAt, &f.Note)
        detail.Followups = append(detail.Followups, f)
    }

    return detail, nil
}

func (r *EventRepo) CreateEvent(name, color string, note string) (int, error) {
    var id int
    err := r.DB.QueryRow(
        "INSERT INTO mined_events (event_name, color, status, mined_at, note) VALUES ($1, $2, 'active', $3, $4) RETURNING id",
        name, color, time.Now(), note,
    ).Scan(&id)
    return id, err
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

func (r *EventRepo) AddFollowup(eventID, actionType, note string) error {
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
        _, err := r.DB.Exec(
            "INSERT INTO mined_event_devices (event_id, device_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            eventID, d,
        )
        if err != nil {
            return err
        }
    }
    return nil
}

func (r *EventRepo) AddIOCs(eventID int, iocs []EventIOC) error {
    for _, ioc := range iocs {
        _, err := r.DB.Exec(
            "INSERT INTO mined_event_iocs (event_id, target, port) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            eventID, ioc.Target, ioc.Port,
        )
        if err != nil {
            return err
        }
    }
    return nil
}

func (r *EventRepo) RemoveDevice(eventID int, deviceID string) error {
    _, err := r.DB.Exec(
        "DELETE FROM mined_event_devices WHERE event_id = $1 AND device_id = $2",
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
```

- [ ] **Step 2: 创建 event_handler.go**

```go
package handler

import (
    "net/http"
    "strconv"
    "strings"
    "time"

    "github.com/gin-gonic/gin"

    "apt-mining-platform/v2/internal/repository"
    "apt-mining-platform/v2/internal/service"
)

type EventHandler struct {
    Repo     *repository.EventRepo
    Extractor *service.IOCExtractor
}

func NewEventHandler(repo *repository.EventRepo, ext *service.IOCExtractor) *EventHandler {
    return &EventHandler{Repo: repo, Extractor: ext}
}

// ListEvents GET /api/events
func (h *EventHandler) ListEvents(c *gin.Context) {
    statusFilter := c.Query("status")
    events, err := h.Repo.ListEvents(statusFilter)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, events)
}

// GetEvent GET /api/events/{id}
func (h *EventHandler) GetEvent(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    detail, err := h.Repo.GetEvent(id)
    if err != nil {
        c.JSON(http.StatusNotFound, gin.H{"error": "event not found"})
        return
    }
    c.JSON(http.StatusOK, detail)
}

// CreateEvent POST /api/events
func (h *EventHandler) CreateEvent(c *gin.Context) {
    var req struct {
        EventName string   `json:"event_name"`
        Color     string   `json:"color"`
        Note      string   `json:"note"`
        Devices   []string `json:"devices"`
        IOCs      []string `json:"iocs"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    id, err := h.Repo.CreateEvent(req.EventName, req.Color, req.Note)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }

    // 添加设备
    if len(req.Devices) > 0 {
        h.Repo.AddDevices(id, req.Devices)
    }

    // 添加 IOC（支持直接字符串解析）
    if len(req.IOCs) > 0 {
        var iocItems []repository.EventIOC
        for _, raw := range req.IOCs {
            if parsed := h.Extractor.ExtractIOCs(raw); len(parsed) > 0 {
                for _, p := range parsed {
                    iocItems = append(iocItems, repository.EventIOC{Target: p.Value, Port: p.Port})
                }
            } else {
                // 如果是 target:port 格式
                parts := strings.SplitN(raw, ":", 2)
                target := parts[0]
                port := ""
                if len(parts) > 1 {
                    port = parts[1]
                }
                iocItems = append(iocItems, repository.EventIOC{Target: target, Port: port})
            }
        }
        h.Repo.AddIOCs(id, iocItems)
    }

    // 自动给设备打标签（如果有）
    // 注意：这里只创建事件，标签通过 events.py 的事件自动打标逻辑处理

    c.JSON(http.StatusCreated, gin.H{"id": id})
}

// UpdateEvent PATCH /api/events/{id}
func (h *EventHandler) UpdateEvent(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    var req struct {
        EventName string `json:"event_name"`
        Color     string `json:"color"`
        Status    string `json:"status"`
        Note      string `json:"note"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    if err := h.Repo.UpdateEvent(id, req.EventName, req.Color, req.Status, req.Note); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// DeleteEvent DELETE /api/events/{id}
func (h *EventHandler) DeleteEvent(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    if err := h.Repo.DeleteEvent(id); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// AddFollowup POST /api/events/{id}/followups
func (h *EventHandler) AddFollowup(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    var req struct {
        ActionType string `json:"action_type"`
        Note       string `json:"note"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    if err := h.Repo.AddFollowup(id, req.ActionType, req.Note); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// AddDevices POST /api/events/{id}/devices
func (h *EventHandler) AddDevices(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    var req struct {
        Devices []string `json:"devices"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    if err := h.Repo.AddDevices(id, req.Devices); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// AddIOCs POST /api/events/{id}/iocs
func (h *EventHandler) AddIOCs(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    var req struct {
        IOCs []string `json:"iocs"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    var iocItems []repository.EventIOC
    for _, raw := range req.IOCs {
        parts := strings.SplitN(raw, ":", 2)
        target := parts[0]
        port := ""
        if len(parts) > 1 {
            port = parts[1]
        }
        iocItems = append(iocItems, repository.EventIOC{Target: target, Port: port})
    }
    if err := h.Repo.AddIOCs(id, iocItems); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// RemoveDevice DELETE /api/events/{id}/devices/{device_id}
func (h *EventHandler) RemoveDevice(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    deviceID := c.Param("device_id")
    if err := h.Repo.RemoveDevice(id, deviceID); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// RemoveIoc DELETE /api/events/{id}/iocs
func (h *EventHandler) RemoveIoc(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    target := c.Query("target")
    port := c.Query("port")
    if err := h.Repo.RemoveIOCs(id, target, port); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}
```

---

### Task 3: 在 main.go 注册事件路由

- [ ] **Step 1: 注册事件路由**

```go
eventRepo := repository.NewEventRepo(database)
iocExtractor := service.NewIOCExtractor()
eventHandler := handler.NewEventHandler(eventRepo, iocExtractor)

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
```

---

### Task 4: 标签管理

**Files:**
- Create: `backend_v2/internal/repository/tag_repo.go`
- Create: `backend_v2/internal/handler/tag_handler.go`

- [ ] **Step 1: 创建 tag_repo.go**

```go
package repository

import (
    "database/sql"
    "strings"
    "time"
)

type TagRepo struct {
    DB *sql.DB
}

func NewTagRepo(db *sql.DB) *TagRepo {
    return &TagRepo{DB: db}
}

type Tag struct {
    ID         int       `json:"id"`
    Name       string    `json:"name"`
    Color      string    `json:"color"`
    IsPermanent bool     `json:"is_permanent"`
    BatchID    *int      `json:"batch_id"`
    CreatedAt  time.Time `json:"created_at"`
    Note       string    `json:"note"`
}

type TagBatch struct {
    ID               int       `json:"id"`
    BatchName        string    `json:"batch_name"`
    CreatedAt        time.Time `json:"created_at"`
    Note             string    `json:"note"`
    Status           string    `json:"status"`
    DeviceIDsSnapshot []string `json:"device_ids_snapshot"`
    TagName          string    `json:"tag_name"`
    Color            string    `json:"color"`
}

func (r *TagRepo) ListTags() ([]Tag, error) {
    rows, _ := r.DB.Query("SELECT id, name, color, is_permanent, batch_id, created_at, note FROM tags ORDER BY created_at DESC")
    defer rows.Close()

    var tags []Tag
    for rows.Next() {
        var t Tag
        rows.Scan(&t.ID, &t.Name, &t.Color, &t.IsPermanent, &t.BatchID, &t.CreatedAt, &t.Note)
        tags = append(tags, t)
    }
    return tags, nil
}

func (r *TagRepo) ListBatches() ([]TagBatch, error) {
    rows, _ := r.DB.Query(`
        SELECT tb.id, tb.batch_name, tb.created_at, tb.note, tb.status,
               tb.device_ids_snapshot, t.name, t.color
        FROM tag_batches tb
        LEFT JOIN tags t ON t.batch_id = tb.id
        ORDER BY tb.created_at DESC
    `)
    defer rows.Close()

    var batches []TagBatch
    for rows.Next() {
        var b TagBatch
        var snapshotJSON sql.NullString
        rows.Scan(&b.ID, &b.BatchName, &b.CreatedAt, &b.Note, &b.Status, &snapshotJSON, &b.TagName, &b.Color)
        if snapshotJSON.Valid {
            // 解析 JSON 数组为 []string
            b.DeviceIDsSnapshot = parseStringArray(snapshotJSON.String)
        }
        batches = append(batches, b)
    }
    return batches, nil
}

func (r *TagRepo) CreateBatch(batchName, tagName, color string, devices []string, note string) (int, error) {
    tx, _ := r.DB.Begin()

    // 创建批次
    var batchID int
    err := tx.QueryRow(
        "INSERT INTO tag_batches (batch_name, created_at, note, status, device_ids_snapshot) VALUES ($1, $2, $3, 'active', $4) RETURNING id",
        batchName, time.Now(), note, toJSONArray(devices),
    ).Scan(&batchID)
    if err != nil {
        tx.Rollback()
        return 0, err
    }

    // 创建标签
    var tagID int
    err = tx.QueryRow(
        "INSERT INTO tags (name, color, is_permanent, batch_id, created_at) VALUES ($1, $2, 0, $3, $4) RETURNING id",
        tagName, color, batchID, time.Now(),
    ).Scan(&tagID)
    if err != nil {
        tx.Rollback()
        return 0, err
    }

    // 批量打标
    for _, d := range devices {
        d = strings.TrimSpace(d)
        if d == "" {
            continue
        }
        // 用 UPPER 统一大小写
        tx.Exec("INSERT INTO device_tags (device_id, tag_id, created_at) VALUES (UPPER($1), $2, $3) ON CONFLICT DO NOTHING", d, tagID, time.Now())
    }

    tx.Commit()
    return batchID, nil
}

func (r *TagRepo) DeleteBatch(batchID int) error {
    // 软删除
    _, err := r.DB.Exec("UPDATE tag_batches SET status = 'deleted' WHERE id = $1", batchID)
    return err
}

func (r *TagRepo) RestoreBatch(batchID int) error {
    _, err := r.DB.Exec("UPDATE tag_batches SET status = 'active' WHERE id = $1", batchID)
    return err
}

func (r *TagRepo) GetDeviceTags(deviceID string) ([]Tag, error) {
    rows, _ := r.DB.Query(`
        SELECT t.id, t.name, t.color
        FROM device_tags dt
        JOIN tags t ON t.id = dt.tag_id
        WHERE UPPER(dt.device_id) = UPPER($1)
        ORDER BY t.name
    `, deviceID)
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

    // 查找或创建标签
    var tagID int
    err := tx.QueryRow("SELECT id FROM tags WHERE name = $1", tagName).Scan(&tagID)
    if err != nil {
        // 标签不存在，创建新的
        err = tx.QueryRow(
            "INSERT INTO tags (name, color, is_permanent, created_at) VALUES ($1, $2, 1, $3) RETURNING id",
            tagName, color, time.Now(),
        ).Scan(&tagID)
        if err != nil {
            tx.Rollback()
            return err
        }
    }

    // 打标（UPPER 统一大小写）
    tx.Exec("INSERT INTO device_tags (device_id, tag_id, created_at) VALUES (UPPER($1), $2, $3) ON CONFLICT DO NOTHING", deviceID, tagID, time.Now())
    tx.Commit()
    return nil
}

func (r *TagRepo) RemoveDeviceTag(deviceID, tagID int) error {
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
            tagName, color, time.Now(),
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

// 工具函数
func parseStringArray(jsonStr string) []string {
    // 简单 JSON 数组解析（可用 encoding/json 替代）
    jsonStr = strings.Trim(jsonStr, "[]")
    if jsonStr == "" {
        return nil
    }
    parts := strings.Split(jsonStr, ",")
    result := make([]string, 0, len(parts))
    for _, p := range parts {
        p = strings.Trim(strings.TrimSpace(p), "\"")
        if p != "" {
            result = append(result, p)
        }
    }
    return result
}

func toJSONArray(arr []string) string {
    if len(arr) == 0 {
        return "[]"
    }
    sb := strings.Builder{}
    sb.WriteString("[")
    for i, s := range arr {
        if i > 0 {
            sb.WriteString(",")
        }
        sb.WriteString("\"")
        sb.WriteString(s)
        sb.WriteString("\"")
    }
    sb.WriteString("]")
    return sb.String()
}
```

- [ ] **Step 2: 创建 tag_handler.go**

```go
package handler

import (
    "net/http"
    "strconv"

    "github.com/gin-gonic/gin"

    "apt-mining-platform/v2/internal/repository"
)

type TagHandler struct {
    Repo *repository.TagRepo
}

func NewTagHandler(repo *repository.TagRepo) *TagHandler {
    return &TagHandler{Repo: repo}
}

// ListTags GET /api/tags
func (h *TagHandler) ListTags(c *gin.Context) {
    tags, err := h.Repo.ListTags()
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, tags)
}

// ListBatches GET /api/tags/batches
func (h *TagHandler) ListBatches(c *gin.Context) {
    batches, err := h.Repo.ListBatches()
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, batches)
}

// CreateBatch POST /api/tags/batches
func (h *TagHandler) CreateBatch(c *gin.Context) {
    var req struct {
        BatchName string   `json:"batch_name"`
        TagName   string   `json:"tag_name"`
        Color     string   `json:"color"`
        Devices   []string `json:"devices"`
        Note      string   `json:"note"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    batchID, err := h.Repo.CreateBatch(req.BatchName, req.TagName, req.Color, req.Devices, req.Note)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusCreated, gin.H{"id": batchID})
}

// DeleteBatch DELETE /api/tags/batches/{id}
func (h *TagHandler) DeleteBatch(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    if err := h.Repo.DeleteBatch(id); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// RestoreBatch POST /api/tags/batches/{id}/restore
func (h *TagHandler) RestoreBatch(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    if err := h.Repo.RestoreBatch(id); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// GetDeviceTags GET /api/tags/devices/{device_id}/tags
func (h *TagHandler) GetDeviceTags(c *gin.Context) {
    deviceID := c.Param("device_id")
    tags, err := h.Repo.GetDeviceTags(deviceID)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, tags)
}

// AddDeviceTag POST /api/tags/devices/tags
func (h *TagHandler) AddDeviceTag(c *gin.Context) {
    var req struct {
        DeviceID string `json:"device_id"`
        TagName  string `json:"tag_name"`
        Color    string `json:"color"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    if err := h.Repo.AddDeviceTag(req.DeviceID, req.TagName, req.Color); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// UpdateTagColor PATCH /api/tags/tags/{tag_id}
func (h *TagHandler) UpdateTagColor(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    var req struct {
        Color string `json:"color"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    if err := h.Repo.UpdateTagColor(id, req.Color); err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// BatchTagDevices POST /api/tags/devices/batch
func (h *TagHandler) BatchTagDevices(c *gin.Context) {
    var req struct {
        Devices []string `json:"devices"`
        TagName string   `json:"tag_name"`
        Color   string   `json:"color"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    count, err := h.Repo.BatchTagDevices(req.Devices, req.TagName, req.Color)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"imported": count})
}

// ImportTextFiles POST /api/tags/batches/import-text-files
func (h *TagHandler) ImportTextFiles(c *gin.Context) {
    form, _ := c.MultipartForm()
    files := form.File["files"]

    imported := 0
    for _, fileHeader := range files {
        file, _ := fileHeader.Open()
        // 读取 TXT 文件内容（每行一个设备ID）
        // ... 解析设备ID并批量打标
        file.Close()
    }

    c.JSON(http.StatusOK, gin.H{"imported": imported})
}
```

---

### Task 5: 追踪管理

**Files:**
- Create: `backend_v2/internal/handler/traced_handler.go`

- [ ] **Step 1: 创建 traced_handler.go**

```go
package handler

import (
    "database/sql"
    "net/http"
    "strconv"
    "strings"
    "time"

    "github.com/gin-gonic/gin"
)

type TracedHandler struct {
    DB *sql.DB
}

func NewTracedHandler(db *sql.DB) *TracedHandler {
    return &TracedHandler{DB: db}
}

// ListTraced GET /api/traced
func (h *TracedHandler) ListTraced(c *gin.Context) {
    keyword := c.Query("keyword")

    query := "SELECT id, target, port, traced_at, note FROM traced_targets"
    args := []interface{}{}
    if keyword != "" {
        query += " WHERE target LIKE $1"
        args = append(args, "%"+keyword+"%")
    }
    query += " ORDER BY traced_at DESC"

    rows, err := h.DB.Query(query, args...)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    defer rows.Close()

    type TracedItem struct {
        ID      int    `json:"id"`
        Target  string `json:"target"`
        Port    string `json:"port"`
        TracedAt string `json:"traced_at"`
        Note    string `json:"note"`
    }

    var items []TracedItem
    for rows.Next() {
        var item TracedItem
        rows.Scan(&item.ID, &item.Target, &item.Port, &item.TracedAt, &item.Note)
        items = append(items, item)
    }
    c.JSON(http.StatusOK, items)
}

// AddTraced POST /api/traced
func (h *TracedHandler) AddTraced(c *gin.Context) {
    // 支持单个或数组
    var req struct {
        Target string `json:"target"`
        Port   string `json:"port"`
        Note   string `json:"note"`
    }

    // 先尝试解析单个
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    _, err := h.DB.Exec(
        "INSERT INTO traced_targets (target, port, traced_at, note) VALUES ($1, $2, $3, $4) ON CONFLICT (target, port) DO UPDATE SET note = EXCLUDED.note",
        req.Target, req.Port, time.Now(), req.Note,
    )
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusCreated, gin.H{"ok": true})
}

// BatchAddTraced POST /api/traced/batch
func (h *TracedHandler) BatchAddTraced(c *gin.Context) {
    var req []struct {
        Target string `json:"target"`
        Port   string `json:"port"`
        Note   string `json:"note"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    for _, item := range req {
        h.DB.Exec(
            "INSERT INTO traced_targets (target, port, traced_at, note) VALUES ($1, $2, $3, $4) ON CONFLICT (target, port) DO UPDATE SET note = EXCLUDED.note",
            item.Target, item.Port, time.Now(), item.Note,
        )
    }
    c.JSON(http.StatusCreated, gin.H{"ok": true})
}

// UpdateTraced PATCH /api/traced/{id}
func (h *TracedHandler) UpdateTraced(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    var req struct {
        Target string `json:"target"`
        Port   string `json:"port"`
        Note   string `json:"note"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }
    _, err := h.DB.Exec(
        "UPDATE traced_targets SET target = $1, port = $2, note = $3 WHERE id = $4",
        req.Target, req.Port, req.Note, id,
    )
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// DeleteTraced DELETE /api/traced/{id}
func (h *TracedHandler) DeleteTraced(c *gin.Context) {
    id, _ := strconv.Atoi(c.Param("id"))
    _, err := h.DB.Exec("DELETE FROM traced_targets WHERE id = $1", id)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// BatchAddTracedFromText POST /api/traced/batch-text
func (h *TracedHandler) BatchAddTracedFromText(c *gin.Context) {
    var req struct {
        Text string `json:"text"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    count := 0
    for _, line := range strings.Split(req.Text, "\n") {
        line = strings.TrimSpace(line)
        if line == "" {
            continue
        }
        parts := strings.SplitN(line, ":", 2)
        target := parts[0]
        port := ""
        if len(parts) > 1 {
            port = parts[1]
        }
        _, err := h.DB.Exec(
            "INSERT INTO traced_targets (target, port, traced_at) VALUES ($1, $2, $3) ON CONFLICT (target, port) DO NOTHING",
            target, port, time.Now(),
        )
        if err == nil {
            count++
        }
    }
    c.JSON(http.StatusOK, gin.H{"imported": count})
}

// ImportTracedExcel POST /api/traced/import
func (h *TracedHandler) ImportTracedExcel(c *gin.Context) {
    file, err := c.FormFile("file")
    if err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": "no file"})
        return
    }
    // 解析 Excel 并批量插入
    // ... 使用 excelize 读取并批量 INSERT
    c.JSON(http.StatusOK, gin.H{"imported": 0})
}
```

---

### Task 6: 设备列表

**Files:**
- Create: `backend_v2/internal/handler/device_handler.go`

- [ ] **Step 1: 创建设备 handler**

```go
package handler

import (
    "database/sql"
    "net/http"
    "strconv"

    "github.com/gin-gonic/gin"
)

type DeviceHandler struct {
    DB *sql.DB
}

func NewDeviceHandler(db *sql.DB) *DeviceHandler {
    return &DeviceHandler{DB: db}
}

// ListDevices GET /api/devices
func (h *DeviceHandler) ListDevices(c *gin.Context) {
    keyword := c.Query("keyword")
    page := parseInt(c.Query("page"), 1)
    pageSize := parseInt(c.Query("page_size"), 50)

    query := `
        SELECT a.device_id,
               COUNT(*) as alert_count,
               MIN(a.first_alert_time) as first_seen,
               MAX(a.last_alert_time) as last_seen
        FROM alerts a
        GROUP BY a.device_id
    `
    if keyword != "" {
        query = "SELECT a.device_id, COUNT(*) as alert_count, MIN(a.first_alert_time) as first_seen, MAX(a.last_alert_time) as last_seen FROM alerts a WHERE a.device_id LIKE $1 GROUP BY a.device_id"
    }
    query += " ORDER BY alert_count DESC LIMIT $2 OFFSET $3"

    var rows *sql.Rows
    var err error
    if keyword != "" {
        rows, err = h.DB.Query(query, "%"+keyword+"%", pageSize, (page-1)*pageSize)
    } else {
        rows, err = h.DB.Query(query, pageSize, (page-1)*pageSize)
    }
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    defer rows.Close()

    type DeviceItem struct {
        DeviceID   string `json:"device_id"`
        AlertCount int    `json:"alert_count"`
        FirstSeen  string `json:"first_seen"`
        LastSeen   string `json:"last_seen"`
    }

    var items []DeviceItem
    for rows.Next() {
        var d DeviceItem
        rows.Scan(&d.DeviceID, &d.AlertCount, &d.FirstSeen, &d.LastSeen)
        items = append(items, d)
    }

    // COUNT
    var total int64
    if keyword != "" {
        h.DB.QueryRow("SELECT COUNT(DISTINCT device_id) FROM alerts WHERE device_id LIKE $1", "%"+keyword+"%").Scan(&total)
    } else {
        h.DB.QueryRow("SELECT COUNT(DISTINCT device_id) FROM alerts").Scan(&total)
    }

    c.JSON(http.StatusOK, gin.H{
        "items":     items,
        "total":     total,
        "page":      page,
        "page_size": pageSize,
    })
}
```

- [ ] **Step 2: 在 main.go 注册所有剩余路由**

```go
tagRepo := repository.NewTagRepo(database)
tagHandler := handler.NewTagHandler(tagRepo)

api.GET("/tags", tagHandler.ListTags)
api.GET("/tags/batches", tagHandler.ListBatches)
api.POST("/tags/batches", tagHandler.CreateBatch)
api.DELETE("/tags/batches/:id", tagHandler.DeleteBatch)
api.POST("/tags/batches/:id/restore", tagHandler.RestoreBatch)
api.GET("/tags/devices/:device_id/tags", tagHandler.GetDeviceTags)
api.POST("/tags/devices/tags", tagHandler.AddDeviceTag)
api.POST("/tags/devices/batch", tagHandler.BatchTagDevices)
api.PATCH("/tags/tags/:id", tagHandler.UpdateTagColor)
api.POST("/tags/batches/import-text-files", tagHandler.ImportTextFiles)

tracedHandler := handler.NewTracedHandler(database)
api.GET("/traced", tracedHandler.ListTraced)
api.POST("/traced", tracedHandler.AddTraced)
api.POST("/traced/batch", tracedHandler.BatchAddTraced)
api.POST("/traced/batch-text", tracedHandler.BatchAddTracedFromText)
api.PATCH("/traced/:id", tracedHandler.UpdateTraced)
api.DELETE("/traced/:id", tracedHandler.DeleteTraced)
api.POST("/traced/import", tracedHandler.ImportTracedExcel)

deviceHandler := handler.NewDeviceHandler(database)
api.GET("/devices", deviceHandler.ListDevices)
```

---

### Task 7: 注册 Config 和 Persistence 路由

**Files:**
- Create: `backend_v2/internal/handler/config_handler.go`

- [ ] **Step 1: 创建 config handler**

```go
package handler

import (
    "net/http"

    "github.com/gin-gonic/gin"

    "apt-mining-platform/v2/internal/config"
)

type ConfigHandler struct {
    Config *config.Config
}

func NewConfigHandler(cfg *config.Config) *ConfigHandler {
    return &ConfigHandler{Config: cfg}
}

// GetConfig GET /api/config
func (h *ConfigHandler) GetConfig(c *gin.Context) {
    c.JSON(http.StatusOK, gin.H{
        "trace_ttl_days":             h.Config.Rules.TraceTTLDays,
        "default_hide_traced":        h.Config.Rules.DefaultHideTraced,
        "default_hide_closed_events": h.Config.Rules.DefaultHideClosedEvts,
        "badges":                     h.Config.Badges,
    })
}

// SaveConfig POST /api/config
func (h *ConfigHandler) SaveConfig(c *gin.Context) {
    var req struct {
        TraceTTLDays          int    `json:"trace_ttl_days"`
        DefaultHideTraced     *bool  `json:"default_hide_traced"`
        DefaultHideClosedEvts *bool  `json:"default_hide_closed_events"`
        Badges                *struct {
            Enabled []string `json:"enabled"`
        } `json:"badges"`
    }
    if err := c.ShouldBindJSON(&req); err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
        return
    }

    // 这里应该更新内存中的配置 + 写回 YAML 文件
    // 简化实现
    if req.TraceTTLDays > 0 {
        h.Config.Rules.TraceTTLDays = req.TraceTTLDays
    }

    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// ReloadDicts POST /api/config/reload
func (h *ConfigHandler) ReloadDicts(c *gin.Context) {
    // 重新加载词典文件
    c.JSON(http.StatusOK, gin.H{"ok": true})
}

// GetDicts GET /api/config/dicts
func (h *ConfigHandler) GetDicts(c *gin.Context) {
    c.JSON(http.StatusOK, gin.H{
        "apt_org":     map[string]string{},
        "crime":       map[string]string{},
        "noise":       map[string]string{},
    })
}
```

- [ ] **Step 2: 注册 config 路由**

```go
configHandler := handler.NewConfigHandler(cfg)

api.GET("/config", configHandler.GetConfig)
api.POST("/config", configHandler.SaveConfig)
api.POST("/config/reload", configHandler.ReloadDicts)
api.GET("/config/dicts", configHandler.GetDicts)

// 保留 persistence 路由（暂时返回空数据）
api.GET("/persistence", func(c *gin.Context) {
    c.JSON(http.StatusOK, []interface{}{})
})
```

---

### Task 8: 提交

```bash
cd backend_v2
git add -A
git commit -m "feat: events, tags, tracing, devices, config APIs

- Event CRUD with IOC extraction (IP, domain, MD5, device ID, URL)
- Event IOC/device associations and followups
- Tag management: batches, batch tagging, TXT import
- Device tagging with UPPER() case normalization
- Traced targets CRUD with batch add
- Device list with keyword search and pagination
- Config get/save endpoints
- All routes registered in main.go"
```

---

## Plan 3 Review 修复记录（2026-05-19）

以下问题基于 Plan 文档伪代码发现，实际 Go 实现中部分已修正、部分本次修复：

### P0 — 路由缺失（前端调用会断）

| # | 问题 | Plan 状态 | 实际代码 | 修复 |
|---|---|---|---|---|
| 1 | `DELETE /api/tags/devices/{device_id}/tags/{tag_id}` 缺失 | Plan 伪代码 `RemoveDeviceTag(deviceID, tagID int)` 签名错误 | ✅ Handler + Route 均已存在，签名正确 `(deviceID string, tagID int)` | 无需修复 |
| 2 | `GET /api/imports/{id}/rows` 未注册路由 | 未提及 | ✅ Handler 存在但 Route 未注册 | ✅ 已注册 |
| 3 | `GET /api/imports/{id}/failures.csv` 未注册路由 | 未提及 | ✅ Handler 存在但 Route 未注册 | ✅ 已注册 |

### P1 — 事务/架构/语义

| # | 问题 | Plan 状态 | 实际代码 | 修复 |
|---|---|---|---|---|
| 4 | `CreateEvent` 无事务：事件/设备/IOC 分开写入 | Plan 伪代码分3步调用，错误被忽略 | ✅ `CreateEventTx` 已包含完整事务（事件+设备+IOC同transaction） | 无需修复 |
| 5 | `isValidIP` 不校验 0-255 范围 | Plan 伪代码只检查段数和数字 | ✅ 实际代码已用 `strconv.Atoi` + `n < 0 \|\| n > 255` | 无需修复 |
| 6 | `isCommonDomain` 定义了 `commonSuffixes` 但未使用 | Plan 伪代码问题 | ✅ 实际代码简洁，无废弃变量 | 无需修复 |
| 7 | `IOCExtractor` 类型缺失（Plan 只定义包级函数） | Plan 定义 `func ExtractIOCs()` | ✅ 实际代码有 `type IOCExtractor struct{}` + `NewIOCExtractor()` | 无需修复 |
| 8 | Traced/Device Handler 直连 `*sql.DB`，违反三层架构 | Plan 伪代码问题 | ❌ 实际代码同样存在 | ✅ 已修复：新增 `TracedRepo` + `DeviceRepo`，Handler 通过 Repo 访问 DB |
| 9 | `ImportTextFiles` 不创建 tag_batches 记录 | Plan 占位 `// ...` | ❌ 实际代码只调 `BatchTagDevices`，无批次记录 | ✅ 已修复：每TXT文件创建 batch（batchName=文件名去.txt） |
| 10 | `ImportTracedExcel` 为 TODO 占位 | Plan 伪代码 `// ...` | ❌ 实际代码返回 `{"imported": 0}` | ✅ 已修复：完整实现 Excel 解析+批量插入 |

### P2 — 配置/契约

| # | 问题 | Plan 状态 | 实际代码 | 修复 |
|---|---|---|---|---|
| 11 | `SaveConfig` 只改内存不写 YAML | Plan 注释"后续可完善" | ✅ 实际代码调用 `config.Save()` 持久化到磁盘 | 无需修复 |
| 12 | `ReloadDicts` 返回空 `ok` | Plan 伪代码 `c.JSON(200, gin.H{"ok": true})` | ❌ 实际代码相同 | ✅ 已修复：添加 `config.ReloadDicts()` + 字典缓存 + 重载逻辑 |
| 13 | `GetDicts` 返回空 map | Plan 伪代码返回空 `map[string]string{}` | ✅ 实际代码已从 YAML 文件读取真实词典 | 无需修复 |
| 14 | `/api/persistence` 返回空数组 | Plan 伪代码 `[]interface{}{}` | ❌ 实际代码相同 | ✅ 已修复：实现完整跨天持续外联查询（GROUP BY source_ip+target, HAVING days>=min_days） |
| 15 | Device 无关键字查询参数位置错误 | Plan 伪代码 `LIMIT $2 OFFSET $3` 缺参数 | ✅ 实际代码 switch-case 分4个函数，参数正确 | 无需修复 |
| 16 | Traced 引入了非标准路由 `/api/traced/batch`、`/api/traced/batch-text` | Plan 引入 | ❌ 实际代码存在 | ✅ 已修复：移除 `/batch`、`/batch-text`；`AddTraced` 改为同时支持单对象和数组 |
| 17 | 标签批次软删除语义不完整 | Plan 只改 `status='deleted'` | ✅ `GetDeviceTags` 已过滤 `tb.status='active'` | 无需修复 |

### P3 — 新增端点补齐

| # | 端点 | 状态 |
|---|---|---|
| 18 | `GET /api/tags/batches/{id}` — 批次详情（含设备列表） | ✅ 已新增 |
| 19 | `DELETE /api/tags/batches/{id}/devices` — 部分设备移除 | ✅ 已新增 |
| 20 | `DELETE /api/imports/all` — 清空全部导入数据 | ✅ 已新增 |
| 21 | `POST /api/imports/reprocess-queued` — 重新处理卡住任务 | ✅ 已新增 |
| 22 | `POST /api/imports/{id}/repair-metadata` — 修复导入元数据 | ✅ 已新增 |

### 当前 API 完整对照

实现后 Go 后端 API 路由与设计文档 [2026-05-18-apt-mining-go-rewrite-design.md](../specs/2026-05-18-apt-mining-go-rewrite-design.md) 契约对齐情况：

| 方法 | 路径 | 状态 |
|---|---|---|
| GET | `/api/health` | ✅ |
| GET | `/api/version` | ✅ |
| GET | `/api/alerts` | ✅ |
| GET | `/api/alerts/options` | ✅ |
| POST | `/api/alerts/export` | ⚠️ 待 Plan 4 |
| GET | `/api/alert-candidates` | ✅ |
| GET | `/api/events` | ✅ |
| POST | `/api/events` | ✅ |
| GET | `/api/events/{id}` | ✅ |
| PATCH | `/api/events/{id}` | ✅ |
| DELETE | `/api/events/{id}` | ✅ |
| POST | `/api/events/{id}/followups` | ✅ |
| POST | `/api/events/{id}/devices` | ✅ |
| POST | `/api/events/{id}/iocs` | ✅ |
| DELETE | `/api/events/{id}/devices/{device_id}` | ✅ |
| DELETE | `/api/events/{id}/iocs` | ✅ |
| GET | `/api/tags` | ✅ |
| GET | `/api/tags/batches` | ✅ |
| GET | `/api/tags/batches/{id}` | ✅ (新增) |
| POST | `/api/tags/batches` | ✅ |
| POST | `/api/tags/batches/import-text-files` | ✅ (TXT→批次) |
| DELETE | `/api/tags/batches/{id}` | ✅ (软删除) |
| POST | `/api/tags/batches/{id}/restore` | ✅ |
| DELETE | `/api/tags/batches/{id}/devices` | ✅ (新增) |
| GET | `/api/tags/devices/{device_id}/tags` | ✅ |
| POST | `/api/tags/devices/tags` | ✅ |
| POST | `/api/tags/devices/batch` | ✅ |
| PATCH | `/api/tags/tags/{id}` | ✅ |
| DELETE | `/api/tags/devices/{device_id}/tags/{tag_id}` | ✅ |
| GET | `/api/traced` | ✅ |
| POST | `/api/traced` | ✅ (单对象+数组) |
| POST | `/api/traced/import` | ✅ (Excel导入) |
| PATCH | `/api/traced/{id}` | ✅ |
| DELETE | `/api/traced/{id}` | ✅ |
| POST | `/api/imports` | ✅ |
| GET | `/api/imports` | ✅ |
| GET | `/api/imports/{id}` | ✅ |
| GET | `/api/imports/{id}/sheets` | ✅ |
| GET | `/api/imports/{id}/rows` | ✅ (路由已注册) |
| GET | `/api/imports/{id}/failures.csv` | ✅ (路由已注册) |
| DELETE | `/api/imports/{id}` | ✅ |
| DELETE | `/api/imports/all` | ✅ (新增) |
| POST | `/api/imports/reprocess-queued` | ✅ (新增) |
| POST | `/api/imports/{id}/repair-metadata` | ✅ (新增) |
| GET | `/api/devices` | ✅ |
| GET | `/api/config` | ✅ |
| POST | `/api/config` | ✅ (持久化到YAML) |
| POST | `/api/config/reload` | ✅ (字典重载) |
| GET | `/api/config/dicts` | ✅ (真实词典) |
| GET | `/api/persistence` | ✅ (完整查询) |

### 架构修正总结

| 维度 | Plan 3 草案 | 修复后 |
|---|---|---|
| Handler→Repo 三层 | Traced/Device 违反 | 全部通过 Repo 层访问 DB |
| 事务边界 | CreateEvent 分步无事务 | CreateEventTx 完整事务 |
| API 契约 | 缺约6个端点，多2个非标准路由 | 补齐缺失，移除非标准 |
| 配置持久化 | 占位/内存 | SaveConfig 写 YAML，ReloadDicts 真重载 |
| IOC 提取 | isValidIP 不校验 | 0-255 完整校验 |
| TXT 批量打标 | 不打批次记录 | 每文件创建 tag_batches |
| 导入追踪 Excel | TODO 占位 | 完整实现 |
| Persistence | 空数组 | 完整跨天查询 |
