# 研判工作台排序/筛选 UX 修复设计

**日期：** 2026-05-08
**阶段：** v3.1 迭代

## 问题

1. **排序误触严重**：点击表头文字或空白区域就触发排序，几乎100%在点击筛选字段时误触排序
2. **筛选按钮太小且与列宽调整按钮过近**：filter 图标 14x14px，resize handle 紧贴右侧
3. **筛选值仅当前页**：`_extractValues` 从 `tableData`（当前页50条）提取，不反映全量数据

## 架构

### 1. 排序按钮替代 sortable

- 移除所有 `el-table-column` 上的 `sortable="custom"` 属性
- 在可排序列（`useColumnConfig.js` 中 `sortable: true`）的表头模板中添加独立排序按钮
- 排序按钮 20x20px，三态循环：无排序 → 降序 → 升序 → 无排序
- 使用 `CaretTop` + `CaretBottom` 图标组合，当前态高亮 `var(--accent)`
- `@click.stop` 阻止事件冒泡

### 2. 筛选图标 + 列宽调整间距

- Filter 图标从 14px 放大到 20px
- 布局：`[文字 flex:1] [排序 20px] [筛选 20px + margin-left:4px + margin-right:6px] [resize 8px]`
- `.resizable-header` 使用 flex 布局对齐
- Element Plus `.el-table th .cell` 通过 `:deep()` 覆盖为 `display: flex; align-items: center`

### 3. 后端 filter_options

- `/api/alert-candidates` 响应新增 `filter_options` 字段
- 从缓存的全量 `all_items` 中提取各列唯一值，不额外查询数据库
- 新增 `_build_filter_options(items)` 函数
- 字段：`device_tags`, `threat_type`, `std_apt_org`, `priority`, `port`, `badges`, `ioc_note`（null）
- 缓存命中/未命中时均返回 `filter_options`

### 4. 前端集成

- `loadData` 时从 `res.filter_options` 更新 `filterOptions` 响应式对象
- `_extractValues` 改为从 `filterOptions` 读取而非遍历 `tableData`
- 新增 `SortButton` 内联组件处理三态排序

## 改动文件

| 文件 | 改动 |
|------|------|
| `backend/api/alerts.py` | 新增 `_build_filter_options` 函数，两处返回注入 `filter_options` |
| `frontend/src/views/Workbench.vue` | 表头模板重构（排序按钮、间距调整）、`_extractValues` 改为读取 `filterOptions` |
| `frontend/src/composables/useColumnConfig.js` | 无需改动（`sortable` 字段已存在） |

## 数据流

```
用户查询 → 后端全量缓存 all_items
         ↓
     _build_filter_options(all_items) → filter_options 字典
         ↓
     响应: { items: 分页数据, filter_options, total, meta }
         ↓
前端 loadData → tableData ← items, filterOptions ← filter_options
         ↓
     _extractValues → 从 filterOptions 读取全量值
         ↓
     筛选弹窗显示所有页面的值
```

## 错误处理

- `filter_options` 为空时 `_extractValues` 返回空数组，筛选弹窗无选项但不报错
- 后端 `_build_filter_options` 对空 items 列表返回空字典
- 排序按钮在 `sortField` 不匹配当前列时显示默认未选中态

## 测试要点

1. 点击表头文字/空白不触发排序
2. 点击排序箭头正确切换三态
3. 点击筛选图标打开弹窗，显示全量筛选选项
4. 筛选生效于所有页的数据（前端显示为当前页过滤后结果）
5. 排序按钮与筛选按钮间距视觉舒适
6. 拖拽列宽不触发排序或筛选
