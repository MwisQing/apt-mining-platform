# 研判工作台排序/筛选 UX 修复实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除研判工作台排序误触，增大筛选按钮间距，筛选选项从全量数据而非当前页获取。

**Architecture:** 后端在 `/api/alert-candidates` 响应中新增 `filter_options` 字段（从缓存全量数据提取）。前端移除 Element Plus `sortable` 属性，改为独立排序按钮（三态循环），filter 图标放大并与 resize handle 拉开间距。

**Tech Stack:** FastAPI + SQLite（后端）/ Vue 3 Composition API + Element Plus（前端）

---

## File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/api/alerts.py` | 修改 | 新增 `_build_filter_options` 函数，两处返回注入 `filter_options` |
| `frontend/src/views/Workbench.vue` | 修改 | 移除 sortable，添加 SortButton 组件，更新 filter 间距，`_extractValues` 改为读取 `filterOptions` |

---

### Task 1: 后端 filter_options 函数

**Files:**
- Modify: `backend/api/alerts.py`

- [ ] **Step 1: 新增 `_build_filter_options` 函数**

在 `_make_items` 函数之后（约 line 511），添加以下函数：

```python
def _build_filter_options(items):
    """Extract unique filter values from ALL candidate items.

    Returns a dict of column key → sorted list of unique values.
    Called on the full cached item list, never triggers extra DB queries.
    """
    result = {}

    # device_tags: union of all tag names
    tag_names = set()
    for item in items:
        for tag in (item.get("device_tags") or []):
            tag_names.add(tag.get("name"))
    result["device_tags"] = sorted(tag_names)

    # threat_type
    result["threat_type"] = sorted({
        item.get("threat_type") for item in items
        if item.get("threat_type")
    })

    # std_apt_org
    result["std_apt_org"] = sorted({
        item.get("std_apt_org") for item in items
        if item.get("std_apt_org")
    })

    # priority: fixed three values
    result["priority"] = ["高优先", "中优先", "观察"]

    # port
    result["port"] = sorted({
        item.get("port") for item in items
        if item.get("port")
    })

    # badges: union of all badge labels
    badge_labels = set()
    for item in items:
        for badge in (item.get("badges") or []):
            badge_labels.add(badge.get("label"))
    result["badges"] = sorted(badge_labels)

    # ioc_note: text input filter, no options list
    result["ioc_note"] = None

    return result
```

- [ ] **Step 2: 缓存命中路径注入 filter_options**

找到 `query_alert_candidates` 中缓存命中的返回块（约 line 1407-1414），在 return 前添加 `filter_options`：

```python
    if cached and (time.time() - cached["ts"]) < CACHE_TTL:
        # Cache hit: re-sort full cached items, page in Python
        all_items = list(cached["items"])  # shallow copy for safe sort
        _sort_candidate_items(all_items, sort_field=sort_field, sort_direction=sort_direction)
        filter_options = _build_filter_options(all_items)
        start = (page - 1) * page_size
        return {
            "items": all_items[start : start + page_size],
            "total": cached["total"],
            "filter_options": filter_options,
            "page": page,
            "page_size": page_size,
            "meta": _candidate_scope_meta(),
            "x_cache": "hit",
        }
```

- [ ] **Step 3: 缓存未命中路径注入 filter_options**

找到 `query_alert_candidates` 中缓存未命中的返回块（约 line 1433-1440），注入 `filter_options`：

```python
    # Sort and page from cache
    _sort_candidate_items(all_items, sort_field=sort_field, sort_direction=sort_direction)
    filter_options = _build_filter_options(all_items)
    start = (page - 1) * page_size
    return {
        "items": all_items[start : start + page_size],
        "total": total,
        "filter_options": filter_options,
        "page": page,
        "page_size": page_size,
        "meta": _candidate_scope_meta(),
        "x_cache": "miss",
    }
```

- [ ] **Step 4: Commit**

```bash
cd "c:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-v3.1"
git add backend/api/alerts.py
git commit -m "feat: add filter_options to /api/alert-candidates response"
```

---

### Task 2: 后端 filter_options 测试

**Files:**
- Modify: `backend/tests/test_imports_helpers.py`（或新建 `backend/tests/test_filter_options.py`）

- [ ] **Step 1: 编写测试**

Create `backend/tests/test_filter_options.py`:

```python
import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.api.alerts import _build_filter_options


class TestBuildFilterOptions(unittest.TestCase):
    def test_empty_items(self):
        result = _build_filter_options([])
        self.assertEqual(result["device_tags"], [])
        self.assertEqual(result["threat_type"], [])
        self.assertEqual(result["std_apt_org"], [])
        self.assertEqual(result["priority"], ["高优先", "中优先", "观察"])
        self.assertEqual(result["port"], [])
        self.assertEqual(result["badges"], [])
        self.assertIsNone(result["ioc_note"])

    def test_single_item(self):
        items = [
            {
                "threat_type": "apt",
                "std_apt_org": "oceanlotus",
                "port": "443",
                "device_tags": [{"id": 1, "name": "重点设备", "color": "#F56C6C"}],
                "badges": [{"name": "apt_dict", "label": "APT词典", "color": "red"}],
                "candidate_priority": {"id": "p1", "label": "高优先", "rank": 1},
            }
        ]
        result = _build_filter_options(items)
        self.assertEqual(result["threat_type"], ["apt"])
        self.assertEqual(result["std_apt_org"], ["oceanlotus"])
        self.assertEqual(result["port"], ["443"])
        self.assertEqual(result["device_tags"], ["重点设备"])
        self.assertEqual(result["badges"], ["APT词典"])

    def test_deduplication(self):
        items = [
            {"threat_type": "apt", "std_apt_org": "oceanlotus", "port": "443", "device_tags": [], "badges": []},
            {"threat_type": "apt", "std_apt_org": "apt29", "port": "443", "device_tags": [], "badges": []},
            {"threat_type": "远控", "std_apt_org": "oceanlotus", "port": "8080", "device_tags": [], "badges": []},
        ]
        result = _build_filter_options(items)
        self.assertEqual(result["threat_type"], ["apt", "远控"])
        self.assertEqual(result["std_apt_org"], ["apt29", "oceanlotus"])
        self.assertEqual(result["port"], ["443", "8080"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试**

Run: `cd "c:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-v3.1" && python -m unittest backend.tests.test_filter_options -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
cd "c:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-v3.1"
git add backend/tests/test_filter_options.py
git commit -m "test: add unit tests for _build_filter_options"
```

---

### Task 3: 前端排序按钮组件 + 移除 sortable

**Files:**
- Modify: `frontend/src/views/Workbench.vue`

- [ ] **Step 1: 导入排序图标**

修改 `Workbench.vue` 第 657 行 import，添加 `CaretTop` 和 `CaretBottom`：

```javascript
import { CaretTop, CaretBottom, Filter, Operation, RefreshRight, Search, StarFilled } from '@element-plus/icons-vue'
```

- [ ] **Step 2: 添加 SortButton 组件**

在 `<script setup>` 中（约 line 690，`sourceIpPreview` 函数之后）添加：

```javascript
function handleSortClick(key) {
  if (sortField.value === key) {
    // Toggle: desc → asc → none
    if (sortOrder.value === 'desc') {
      sortOrder.value = 'asc'
    } else {
      sortField.value = ''
      sortOrder.value = ''
    }
  } else {
    // First click: default to desc
    sortField.value = key
    sortOrder.value = 'desc'
  }
  currentPage.value = 1
  loadData()
}
```

在 `<template>` 中，`</template>` 之前，添加 SortButton 组件模板（作为可复用的内联模板，在 script 中注册）：

在 `<script setup>` 底部添加：

```javascript
const SortButton = {
  props: ['active', 'order', 'columnKey'],
  components: { CaretTop, CaretBottom },
  template: `
    <span
      class="sort-button"
      :class="{ 'is-active': active === columnKey }"
      @click.stop="$emit('sort', columnKey)"
      title="排序"
    >
      <CaretTop :class="{ active: active === columnKey && order === 'asc' }" />
      <CaretBottom :class="{ active: active === columnKey && order === 'desc' }" />
    </span>
  `,
  emits: ['sort'],
}
```

- [ ] **Step 3: 移除所有 sortable="custom"**

将以下列中的 `sortable="custom"` 全部移除（改为空）：
- `score` 列（line 156）
- `device_id` 列（line 174）
- `device_target_count` 列（line 277）
- `source_ip` 列（line 295）
- `source_ip_count` 列（line 319）
- `target` 列（line 337）
- `port` 列（line 355）
- `device_alert_count` 列（line 391）
- `threat_type` 列（line 461）
- `std_apt_org` 列（line 496）
- `heat` 列（line 544）

注意：`analysis_status` 列和 `is_focused` 列没有 `sortable="custom"`，无需改动。

- [ ] **Step 4: 在每个可排序列的表头添加 SortButton**

对于以下每个列（它们的 `sortable: true` 定义在 `useColumnConfig.js`），在其 `<template #header>` 的 `.resizable-header` 内，在 `col-label-text` 之后、filter 图标（或 resize handle）之前，插入 `<SortButton>`：

**score 列**（原 line 159-164）：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('score') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="score" @sort="handleSortClick" />
    <span class="resize-handle" @mousedown.stop="onResizeStart('score', $event)"></span>
  </div>
</template>
```

**device_id 列**：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('device_id') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="device_id" @sort="handleSortClick" />
    <span class="resize-handle" @mousedown.stop="onResizeStart('device_id', $event)"></span>
  </div>
</template>
```

**device_target_count 列**：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('device_target_count') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="device_target_count" @sort="handleSortClick" />
    <span class="resize-handle" @mousedown.stop="onResizeStart('device_target_count', $event)"></span>
  </div>
</template>
```

**source_ip 列**：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('source_ip') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="source_ip" @sort="handleSortClick" />
    <span class="resize-handle" @mousedown.stop="onResizeStart('source_ip', $event)"></span>
  </div>
</template>
```

**source_ip_count 列**：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('source_ip_count') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="source_ip_count" @sort="handleSortClick" />
    <span class="resize-handle" @mousedown.stop="onResizeStart('source_ip_count', $event)"></span>
  </div>
</template>
```

**target 列**：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('target') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="target" @sort="handleSortClick" />
    <span class="resize-handle" @mousedown.stop="onResizeStart('target', $event)"></span>
  </div>
</template>
```

**port 列**（带 filter）：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('port') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="port" @sort="handleSortClick" />
    <el-popover trigger="click" :width="220" placement="bottom-end">
      <template #reference>
        <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('port') }">
          <Filter />
        </el-icon>
      </template>
      <div class="column-filter">
        <el-checkbox-group v-model="columnFilters.port" class="column-filter-group">
          <el-checkbox v-for="val in _extractValues('port')" :key="val" :label="val" :value="val">
            {{ val || '(空)' }}
          </el-checkbox>
        </el-checkbox-group>
        <div class="column-filter__actions">
          <el-button size="small" text @click="columnFilters.port = _extractValues('port')">全选</el-button>
          <el-button size="small" text @click="clearFilter('port')">清空</el-button>
        </div>
      </div>
    </el-popover>
    <span class="resize-handle" @mousedown.stop="onResizeStart('port', $event)"></span>
  </div>
</template>
```

**device_alert_count 列**：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('device_alert_count') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="device_alert_count" @sort="handleSortClick" />
    <span class="resize-handle" @mousedown.stop="onResizeStart('device_alert_count', $event)"></span>
  </div>
</template>
```

**threat_type 列**（带 filter）：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('threat_type') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="threat_type" @sort="handleSortClick" />
    <el-popover trigger="click" :width="220" placement="bottom-end">
      <template #reference>
        <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('threat_type') }">
          <Filter />
        </el-icon>
      </template>
      <div class="column-filter">
        <el-checkbox-group v-model="columnFilters.threat_type" class="column-filter-group">
          <el-checkbox v-for="val in _extractValues('threat_type')" :key="val" :label="val" :value="val">
            {{ val }}
          </el-checkbox>
        </el-checkbox-group>
        <div class="column-filter__actions">
          <el-button size="small" text @click="columnFilters.threat_type = _extractValues('threat_type')">全选</el-button>
          <el-button size="small" text @click="clearFilter('threat_type')">清空</el-button>
        </div>
      </div>
    </el-popover>
    <span class="resize-handle" @mousedown.stop="onResizeStart('threat_type', $event)"></span>
  </div>
</template>
```

**std_apt_org 列**（带 filter）：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('std_apt_org') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="std_apt_org" @sort="handleSortClick" />
    <el-popover trigger="click" :width="220" placement="bottom-end">
      <template #reference>
        <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('std_apt_org') }">
          <Filter />
        </el-icon>
      </template>
      <div class="column-filter">
        <el-checkbox-group v-model="columnFilters.std_apt_org" class="column-filter-group">
          <el-checkbox v-for="val in _extractValues('std_apt_org')" :key="val" :label="val" :value="val">
            {{ val }}
          </el-checkbox>
        </el-checkbox-group>
        <div class="column-filter__actions">
          <el-button size="small" text @click="columnFilters.std_apt_org = _extractValues('std_apt_org')">全选</el-button>
          <el-button size="small" text @click="clearFilter('std_apt_org')">清空</el-button>
        </div>
      </div>
    </el-popover>
    <span class="resize-handle" @mousedown.stop="onResizeStart('std_apt_org', $event)"></span>
  </div>
</template>
```

**heat 列**：
```vue
<template #header>
  <div class="resizable-header">
    <span class="col-label-text">{{ colLabel('heat') }}</span>
    <SortButton :active="sortField" :order="sortOrder" column-key="heat" @sort="handleSortClick" />
    <span class="resize-handle" @mousedown.stop="onResizeStart('heat', $event)"></span>
  </div>
</template>
```

**注意**：`priority` 列没有 `sortable` 属性，但有 filter。保持其 filter 图标和 resize handle 不变，不添加排序按钮。其余无 `sortable="custom"` 的列也不添加排序按钮。

- [ ] **Step 5: Commit**

```bash
cd "c:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-v3.1"
git add frontend/src/views/Workbench.vue
git commit -m "feat: replace sortable with independent sort buttons in workbench table headers"
```

---

### Task 4: 前端筛选图标间距 + filterOptions 数据源

**Files:**
- Modify: `frontend/src/views/Workbench.vue`

- [ ] **Step 1: 更新 `_extractValues` 为读取 `filterOptions`**

替换现有的 `_extractValues` 函数（约 line 873-891）：

```javascript
function _extractValues(key) {
  if (key === 'priority') return ['高优先', '中优先', '观察']
  return (filterOptions.value[key] || []).slice()
}
```

- [ ] **Step 2: 新增 `filterOptions` 响应式变量**

在 `columnFilters` 定义之后（约 line 856），添加：

```javascript
const filterOptions = ref({})
```

- [ ] **Step 3: 在 `loadData` 中更新 `filterOptions`**

修改 `loadData` 函数中 `tableData.value` 赋值之后（约 line 817），添加：

```javascript
    const res = await fetchCandidates(params)
    if (requestId !== requestSeq) return
    tableData.value = res.items || []
    total.value = res.total || 0
    if (res.filter_options) {
      filterOptions.value = res.filter_options
    }
```

- [ ] **Step 4: 更新 CSS**

在 `<style scoped>` 中，修改以下样式：

将 `.header-filter-icon`（约 line 1099-1106）改为：

```css
.header-filter-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  cursor: pointer;
  color: var(--text-muted);
  transition: color 0.15s;
  position: relative;
  margin-left: 4px;
  margin-right: 6px;
}
```

添加 `.sort-button` 样式：

```css
.sort-button {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
  gap: 0;
  line-height: 1;
}
.sort-button:hover {
  background: var(--bg-tertiary);
}
.sort-button.is-active {
  color: var(--accent);
}
.sort-button :deep(.active) {
  color: var(--accent);
}
.sort-button :deep(svg) {
  width: 12px;
  height: 12px;
}
```

- [ ] **Step 5: 移除 `handleSortChange` 函数引用**

确保 `el-table` 上的 `@sort-change="handleSortChange"` 被移除（因为我们不再依赖 Element Plus 的排序事件）。`handleSortChange` 函数本身可以保留，但不再使用。或者删除它：

```javascript
// Remove handleSortChange function entirely
// Remove @sort-change="handleSortChange" from el-table
```

- [ ] **Step 6: Commit**

```bash
cd "c:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-v3.1"
git add frontend/src/views/Workbench.vue
git commit -m "feat: use filterOptions from API for full-data filtering, update icon spacing"
```

---

### Task 5: 前端构建 + 后端回归验证

**Files:**
- N/A (validation only)

- [ ] **Step 1: 前端构建**

Run: `cd "c:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-v3.1\frontend" && npm run build`
Expected: Build succeeds (Element Plus CSS warnings ok, no errors)

- [ ] **Step 2: 后端单元测试**

Run: `cd "c:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-v3.1" && python -m unittest backend.tests.test_filter_options -v`
Expected: All tests pass

- [ ] **Step 3: Commit if any fixes needed**

```bash
cd "c:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-v3.1"
git add .
git commit -m "build: verify frontend build + backend tests"
```
