# 侧边栏收拢/展开功能设计

## 概述

为研判工作台左侧导航栏增加收拢/展开功能，收拢后宽度从 240px 缩至 64px，仅保留图标，最大化内容区可视空间。

## 交互方案

- **触发按钮**：侧边栏顶部品牌行右侧放置箭头按钮（ArrowLeft / ArrowRight）
- **收拢状态**：宽度 64px，隐藏品牌文字、导航文字、底部状态栏，仅居中显示图标
- **展开状态**：宽度 240px，恢复全部文字和信息
- **过渡动画**：`grid-template-columns` 使用 `transition: width 0.25s ease`，内部元素 `opacity` + `max-width` 同步过渡
- **Tooltip**：收拢时 hover 图标显示 Element Plus `el-tooltip` 标签（如"研判工作台"）
- **状态持久化**：`localStorage` 保存 `sidebar-collapsed` 键，刷新后保持用户偏好

## 技术实现

### 文件改动

仅修改 `frontend/src/App.vue`。

### 新增状态

```js
const isCollapsed = ref(false)
```

### 布局变化

`grid-template-columns` 动态绑定：
- 展开：`240px 1fr`
- 收拢：`64px 1fr`

### 收拢时元素处理

| 元素 | 收拢行为 |
|------|----------|
| 箭头按钮 | 保留，方向翻转 |
| 品牌标识图标 | 保留，居中 |
| 品牌文字 | 隐藏（`opacity: 0; max-width: 0`） |
| 导航图标 | 保留，居中 |
| 导航文字 | 隐藏（`max-width: 0; overflow: hidden`） |
| Tooltip | 激活 |
| 底部主题切换 | 隐藏 |
| 底部地址/版本 | 隐藏 |

### 动画细节

```css
.sidebar {
  transition: width 0.25s ease;
}
.brand-copy,
.nav-item__content,
.sidebar-footer {
  transition: opacity 0.2s ease, max-width 0.25s ease;
}
```

### 图标选择

使用 Element Plus Icons：`ArrowLeft`（展开状态）→ `ArrowRight`（收拢状态）
