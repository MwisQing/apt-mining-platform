# APT Mining Workbench v4.19 — 功能补全设计（3个独立页面）

> **状态**：已审批 | **日期**：2026-05-28 | **方向**：方向 A（独立页面）

---

## 1. 概述

从用户角度补全 3 项缺失功能：告警人工标注、审计日志查看、设备维度管理。每个功能作为独立页面 + 路由，不嵌入现有页面。

---

## 2. 告警标注页（AlertAnnotation）

### 2.1 用途

对单条告警进行人工标注：设置分析状态、是否重点、添加备注。后端接口 `PATCH /api/alerts/:id/annotation` 已存在但无 UI 调用。

### 2.2 路由

| 字段 | 值 |
|------|---|
| 路径 | `/annotations` |
| 侧边栏 | 排在「原始告警」下方 |
| 标题 | 告警标注 |

### 2.3 前端

**文件**：`frontend/src/views/AlertAnnotation.vue`

**API**：复用 `src/api/alerts.js` 的 `annotateAlert(id, data)` 和 `listAlerts(params)`

**布局**：
- 筛选栏：日期范围选择器、威胁类型下拉、关键词输入框
- 主体：el-table 展示告警（设备ID、源IP、目标、端口、威胁类型、威胁等级、分析状态、是否重点、最后操作时间）
- 操作列：点击弹出 el-dialog 标注编辑
  - `analysis_status`：el-select（未分析 / 分析中 / 已完成）
  - `is_focused`：el-switch
  - `note`：el-input textarea
  - 保存按钮 → 调用 `PATCH /api/alerts/:id/annotation`

**分页**：服务端分页，默认每页 50 条

### 2.4 后端

无需改动。`PATCH /api/alerts/:id/annotation` 已实现于 `candidate_handler.go`，更新 `alerts` 表的 `analysis_status`、`is_focused`、`annotation_note` 字段。

---

## 3. 审计日志页（AuditLog）

### 3.1 用途

查看系统操作记录：谁在何时做了什么（创建事件、打标签、删除导入等）。数据库 `audit_log` 表已存在但无 API 和 UI。

### 3.2 路由

| 字段 | 值 |
|------|---|
| 路径 | `/audit` |
| 侧边栏 | 最底部（管理类） |
| 标题 | 审计日志 |

### 3.3 前端

**文件**：`frontend/src/views/AuditLog.vue`

**新 API 封装**：`src/api/audit.js`
- `listAuditLogs(params)` → `GET /api/audit-log`

**布局**：
- 筛选栏：时间范围选择器、操作类型下拉（create/update/delete/import）、关键词搜索
- 主体：el-table 只读展示（时间 | 操作类型 | 目标对象 | 详情摘要 | 操作人/IP）
- 无编辑/删除操作
- 底部：服务端分页器

### 3.4 后端新增

**文件**：`backend_v2/internal/handler/audit_handler.go`（新建）

**端点**：`GET /api/audit-log`

**参数**：
- `date_start` / `date_end`：时间范围
- `action_type`：操作类型过滤
- `keyword`：关键词搜索（LIKE 匹配 target_object + detail）
- `page` / `page_size`：分页

**响应**：
```json
{
  "items": [{
    "id", "created_at", "user_id", "action_type",
    "target_object", "detail", "ip"
  }],
  "total", "page", "page_size"
}
```

**数据库层**：`backend_v2/internal/repository/audit_repo.go`（新建）
- 读 `audit_log` 表，支持分页+筛选

**路由注册**：`main.go` 注册 `r.GET("/api/audit-log", h.GetAuditLogs)`

---

## 4. 设备管理页（DeviceManager）

### 4.1 用途

按设备维度查看和管理：设备标签、关联事件、告警统计、备注。

### 4.2 路由

| 字段 | 值 |
|------|---|
| 路径 | `/devices` |
| 侧边栏 | 排在「事件管理」下方 |
| 标题 | 设备管理 |

### 4.3 前端

**文件**：`frontend/src/views/DeviceManager.vue`

**API**：
- 复用 `src/api/tags.js` 的 `getDeviceTags(deviceId)`
- 新增 `src/api/devices.js`：
  - `listDevices(params)` → `GET /api/devices`
  - `addDeviceTag(deviceId, tagNames)` → `POST /api/devices/:id/tags`
  - `removeDeviceTag(deviceId, tagName)` → `DELETE /api/devices/:id/tags`

**布局**：
- 顶部：关键词搜索（设备ID）、标签筛选（多选下拉）
- 主体：el-table
  - 设备ID（可复制）| 关联标签（tag chips）| 关联事件数 | 告警数 | 最后活跃时间 | 设备备注 | 操作
  - 操作列：编辑标签（el-dialog 选标签批量绑定/解绑）、查看事件（跳转到 EventManager 并过滤）
- 底部：服务端分页器

### 4.4 后端增强

**现有端点**：`GET /api/devices` 已存在于 `device_handler.go`，但返回简单列表

**增强**：
- 设备列表查询新增关联字段：关联事件数（COUNT from `mined_event_devices`）、标签列表（JOIN `device_tags`）、告警数（COUNT from `alerts`）、最后活跃时间（MAX `first_alert_time`）
- 新增 `POST /api/devices/:id/tags` — 为设备批量绑定标签
- 新增 `DELETE /api/devices/:id/tags` — 为设备解绑标签

**数据库层**：`backend_v2/internal/repository/device_repo.go`（增强现有）
- `ListDevices()` 增加 JOIN 子查询
- `AddDeviceTags(deviceId, tagNames)` 新增
- `RemoveDeviceTag(deviceId, tagName)` 新增

---

## 5. 侧边栏更新

`App.vue` 导航菜单新增 3 个条目：

| 顺序 | 图标 | 文字 | 路由 |
|------|------|------|------|
| 1 | Monitor | 研判工作台 | `/` |
| 2 | List | 原始告警 | `/alerts` |
| 3 | EditPen | 告警标注 | `/annotations` |
| 4 | Connection | 事件管理 | `/events` |
| 5 | Monitor | 设备管理 | `/devices` |
| 6 | Notebook | IOC备注 | `/ioc-notes` |
| 7 | Setting | 导入与设置 | `/settings` |
| 8 | Document | 审计日志 | `/audit` |

---

## 6. 实施顺序

1. **审计日志后端**（audit_handler.go + audit_repo.go + 路由注册）
2. **设备管理后端增强**（device_repo.go JOIN + 标签绑定/解绑接口）
3. **告警标注页前端**（AlertAnnotation.vue + 路由）
4. **审计日志页前端**（AuditLog.vue + api/audit.js + 路由）
5. **设备管理页前端**（DeviceManager.vue + api/devices.js + 路由）
6. **侧边栏更新**（App.vue 新增 3 个导航条目）
7. **回归测试**（`scripts/test_api.py` 全量通过）

---

## 7. 约束与边界

- 每个新 Vue 文件 ≤ 400 行（超则拆分 composables）
- 每个新 Go 文件 ≤ 400 行
- 不修改现有页面逻辑（仅新增路由和侧边栏）
- 审计日志为只读，不提供删除/编辑接口
- 设备管理只增强查询和标签绑定，不改事件关联逻辑
