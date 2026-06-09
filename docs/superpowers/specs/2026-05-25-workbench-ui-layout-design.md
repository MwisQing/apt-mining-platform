# 研判工作台 UI 布局优化设计

> 日期: 2026-05-25
> 状态: 已批准

## 目标

优化研判工作台（Workbench）的滚动体验和侧栏交互，解决 3 个可用性问题：

1. 垂直滚动条出现在"候选清单"卡片内部，而非页面最右边
2. 左侧导航栏不支持手动收拢
3. 水平滚动条在表格最底部，需要滚到底才可见

## 设计决策

### 1. 垂直滚动条贴最右边

**当前问题：** `.table-scroll` 嵌套在多层容器中（`.content-pane` → `.workbench` → `.table-card` → `.table-scroll`），滚动条深陷页面中间。

**方案：**
- `.content-pane` 移除 `overflow`，改为由 `.workbench` 使用 CSS Grid 两行布局
- 第一行 `.filter-bar` 固定在顶部（sticky）
- 第二行 `.table-scroll` 占满剩余空间（`overflow-y: auto`），右边缘紧贴 `.content-pane` 内壁
- 结果：垂直滚动条在表格区域最右边，与屏幕右边缘对齐

### 2. 水平滚动条顶部吸底

**当前问题：** 水平滚动条在表格最底部，需要滚到底才可见。

**方案：**
- 在表格上方新增 `.table-scroll-h-bar` 容器（高度 14px），内部放一个与表格等宽的 `div`
- 用 `ResizeObserver` 监听表格内容宽度变化
- 双向同步：顶部滚动条 `scrollLeft` ↔ 表格 `scrollLeft`
- 仅在表格内容溢出水平方向时显示（`overflow-x: auto`）

### 3. 左侧导航收拢至 64px 图标模式

**方案：**
- `App.vue` 新增 `sidebarCollapsed` 状态（默认展开）
- 侧栏顶部新增收拢/展开按钮
- 收拢时：
  - `.app-shell` 的 `grid-template-columns` 从 `240px 1fr` 切换为 `64px 1fr`
  - 品牌文字和 `sidebar-footer` 隐藏
  - `.nav-item__label` 隐藏，只保留图标
  - 收拢按钮变为展开按钮
- 状态保存到 `localStorage`（key: `apt-sidebar-collapsed`）
- 过渡动画 300ms

## 涉及文件

| 文件 | 改动范围 |
|------|----------|
| `frontend/src/App.vue` | 侧栏收拢状态、按钮、grid 切换、过渡动画 |
| `frontend/src/views/Workbench.vue` | CSS Grid 两行布局、顶部水平滚动条、scroll 同步逻辑 |
| `frontend/src/styles/global.css` | 侧栏收拢时的全局样式补充 |

## 验收标准

- [ ] 垂直滚动条出现在页面最右边，而非"候选清单"卡片内部
- [ ] 筛选栏在滚动时保持可见（sticky）
- [ ] 水平滚动条在表格顶部始终可见（当内容溢出时）
- [ ] 左侧导航可收拢至 64px 图标模式，只保留图标
- [ ] 左侧导航可展开回 240px，状态在页面刷新后保持
