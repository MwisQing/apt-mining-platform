---
name: 测试端口隔离 + 中键导航 + 标签排除
description: 三项功能：测试环境端口隔离（9099）、侧边栏中键新标签页打开、研判工作台设备标签排除筛选
type: project
---

# 设计文档：测试端口隔离 + 中键导航 + 标签排除

## 1. 测试端口隔离

### 背景
测试和正式环境在同一台机器上运行时，共用 8088 端口会产生冲突。

### 方案
新建 `start-test.bat` 和 `stop-test.bat`，使用端口 9099。

#### start-test.bat
- 端口检测：检测并清理 9099 端口占用（而非 8088）
- 启动命令：`uvicorn ... --port 9099`
- 浏览器提示：`http://127.0.0.1:9099`
- **临时修改** `frontend/vite.config.js` 中 proxy target 为 `http://127.0.0.1:9099`（支持 `npm run dev` 开发模式联调）

#### stop-test.bat
- 端口检测：仅检测 9099 端口（而非 8088）
- **恢复** `frontend/vite.config.js` 中 proxy target 为 `http://127.0.0.1:8088`

#### 不受影响的文件
- `config/config.yaml` — server.port 仅作为参考值，后端不使用它
- `frontend/package.json` — 无端口硬编码
- `frontend/src/api/index.js` — baseURL 为空字符串，跟随当前 host

### 风险评估与恢复
- vite.config.js 使用 PowerShell `-replace` 替换端口数字，不做文件备份
- start-test.bat 启动时检测当前值，如非 9099 则替换为 9099
- stop-test.bat 停止时检测当前值，如非 8088 则替换回 8088
- 幂等：即使 start-test.bat 被 Ctrl+C 中断，下次 stop-test.bat 仍能恢复
- 正则精确匹配 `http://127.0.0.1:8088` → `http://127.0.0.1:9099`，避免误替换

## 2. 侧边栏导航中键新标签页打开

### 背景
App.vue 侧边栏使用 `<button @click="router.push()">`，不支持浏览器原生中键打开。之前应该支持，后来被改成了 button。

### 方案
将 `App.vue` 中 `<button class="nav-item">` 改为 `<router-link class="nav-item" :to="item.path">`

`<router-link>` 底层渲染为 `<a href="...">`，Vue Router 拦截左键实现 SPA 跳转，中键/右键由浏览器原生处理。

### 具体改动
- `frontend/src/App.vue` 第 16-30 行：`<button>` → `<router-link>`
- 移除 `@click="navigate()"`，改为 `:to="item.path"`
- `navigate()` 函数保留（其他地方无直接调用），但 nav-item 不再使用它。

## 3. 设备标签排除筛选

### 背景
设备会命中多个标签（如「重点设备」+「近期不看」）。用户想筛选重点设备，但同时排除也带「近期不看」标签的设备。

### 后端改动

#### 后端改动细节

`_build_where()` 已接受 `device_tags` 参数做包含查询，排除标签同样走这条路：
```python
def _build_where(
    *,
    ...
    device_tags=None,
    exclude_device_tags=None,  # 新增
    ...
):
```
在 `device_tags` EXISTS 子查询之后，新增 NOT EXISTS 子查询：
```sql
AND NOT EXISTS (
  SELECT 1 FROM device_tags dt
  WHERE dt.device_id = a.device_id AND dt.tag_id IN (:et_0, :et_1, ...)
)
```

#### `_candidate_scope_meta()` / cache key
`_cache_key_for_params()` 已经对 filter params 做 MD5，只要 `exclude_device_tags` 参数出现在传入字典中，缓存 key 会自动变化，无需额外处理。但需确保：
- `/api/alert-candidates` 的 `cache_filter` 字典包含 `exclude_device_tags`
- `_base_filter_params()` 接受并传递 `exclude_device_tags`

#### 前端改动

##### `frontend/src/views/Workbench.vue`
- 顶部筛选栏（filter-row）新增排除标签下拉框，放在「隐藏已追踪」开关右侧：
  ```html
  <el-select
    v-model="excludeTags"
    multiple
    filterable
    placeholder="排除标签"
    size="small"
    class="filter-item"
    @change="handleSearch"
  >
    <el-option v-for="tag in tagOptions" :key="tag.id" :label="tag.name" :value="tag.id" />
  </el-select>
  ```
- `handleSearch()` 中传入 `exclude_device_tags` 参数
- `loadData()` 中将 `excludeTags` 数组转为逗号分隔字符串传给后端

## 4. 影响范围

| 文件 | 改动 |
|------|------|
| `start-test.bat` | 新建 |
| `stop-test.bat` | 新建 |
| `frontend/vite.config.js` | 运行 start-test.bat 时临时修改 |
| `frontend/src/App.vue` | button → router-link |
| `frontend/src/views/Workbench.vue` | 新增排除标签下拉框 |
| `backend/api/alerts.py` | 新增 exclude_device_tags 参数 |
