# Sidebar Collapse/Expand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapse/expand toggle to the left sidebar, shrinking from 240px to 64px (icon-only mode) with smooth animation and localStorage persistence.

**Architecture:** Single-file change in `App.vue` — add `isCollapsed` reactive state, dynamic grid width, arrow toggle button, conditional visibility for text/brand/footer elements, and `el-tooltip` on nav icons when collapsed.

**Tech Stack:** Vue 3 Composition API, Element Plus, CSS transitions

---

### Task 1: Add collapse state + arrow button

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add ArrowLeft import + isCollapsed state**

In the `<script setup>` block, add `ArrowLeft` to the existing icon imports (after `Setting`), and add the `isCollapsed` state:

```js
// Add to imports:
ArrowLeft,

// After the existing ref declarations:
const isCollapsed = ref(localStorage.getItem('sidebar-collapsed') === 'true')
function toggleSidebar() {
  isCollapsed.value = !isCollapsed.value
  localStorage.setItem('sidebar-collapsed', isCollapsed.value)
}
```

- [ ] **Step 2: Add arrow button to brand row**

In the template, inside `.brand-card`, add the arrow button on the right side:

```vue
<div class="brand-card">
  <div class="brand-mark">
    <el-icon :size="18"><Monitor /></el-icon>
  </div>
  <div class="brand-copy">
    <div class="brand-title">APT Mining</div>
    <div class="brand-subtitle">Workbench</div>
  </div>
  <button class="collapse-btn" @click="toggleSidebar" title="Toggle sidebar">
    <el-icon :size="14"><ArrowLeft /></el-icon>
  </button>
</div>
```

- [ ] **Step 3: Add CSS for the collapse button**

Add these styles inside `<style scoped>` (after `.brand-subtitle` block):

```css
.collapse-btn {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
  flex-shrink: 0;
  margin-left: auto;
}

.collapse-btn:hover {
  background: var(--sidebar-active);
  color: var(--text-primary);
}
```

- [ ] **Step 4: Verify build**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds with no errors.

- [ ] **Step 5: Sync static files**

Run (from project root):
```bash
python -c "import shutil; shutil.copytree('frontend/dist', 'backend_v2/static', dirs_exist_ok=True)"
```

- [ ] **Step 6: Test manually**

Start the app (`python dev.py`), open browser, verify:
- Arrow button appears on the right of the brand row
- Clicking the arrow does nothing yet visually (state exists but no layout change yet)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: add sidebar collapse toggle button and state"
```

---

### Task 2: Dynamic sidebar width + hide text on collapse

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Bind dynamic grid width to app-shell**

Change the `.app-shell` inline style binding:

```vue
<div class="app-shell" :class="{ 'app-shell--collapsed': isCollapsed }">
```

Replace the hardcoded `grid-template-columns: 240px minmax(0, 1fr)` in CSS with the class-based approach. Add this new rule in `<style scoped>`:

```css
.app-shell--collapsed {
  grid-template-columns: 64px minmax(0, 1fr) !important;
}
```

And change the base `.app-shell` rule to have a transition:

```css
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  background: var(--bg-primary);
  transition: grid-template-columns 0.25s ease;
}
```

- [ ] **Step 2: Add sidebar width transition + collapsed class**

Update the `.sidebar` element:

```vue
<aside class="sidebar" :class="{ 'sidebar--collapsed': isCollapsed }">
```

Add CSS:

```css
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 20px 14px 14px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border-strong);
  transition: padding 0.25s ease, width 0.25s ease;
}

.sidebar--collapsed {
  padding: 20px 8px 8px;
}

.sidebar--collapsed .brand-copy {
  opacity: 0;
  max-width: 0;
  overflow: hidden;
  transition: opacity 0.15s ease, max-width 0.25s ease;
}

.sidebar--collapsed .sidebar-footer {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
  transition: opacity 0.15s ease, max-height 0.25s ease;
}
```

- [ ] **Step 3: Hide nav text on collapse**

Update the `.nav-item__content` to respond to collapse:

```css
.sidebar--collapsed .nav-item__content {
  opacity: 0;
  max-width: 0;
  overflow: hidden;
  transition: opacity 0.15s ease, max-width 0.25s ease;
}

.sidebar--collapsed .nav-item {
  justify-content: center;
  padding: 10px 0;
}

.sidebar--collapsed .nav-item__icon {
  margin: 0;
}
```

- [ ] **Step 4: Verify build**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 5: Sync static files + manual test**

Sync `frontend/dist/` → `backend_v2/static/`, then start app and verify:
- Click arrow → sidebar shrinks to 64px, text fades out, icons centered
- Click arrow again → sidebar expands back to 240px with text
- Animation is smooth (~250ms)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: sidebar collapses to icon-only mode with animation"
```

---

### Task 3: Tooltips + theme persistence + final polish

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Wrap nav items with el-tooltip**

Change the nav section to use `el-tooltip` on each item. Replace the existing `nav-section` block:

```vue
<div class="nav-section">
  <el-tooltip
    v-for="item in navItems"
    :key="item.path"
    :content="item.label"
    :disabled="!isCollapsed"
    placement="right"
    :show-after="200"
  >
    <router-link
      :to="item.path"
      class="nav-item"
      :class="{ 'nav-item--active': route.path === item.path }"
      active-class="nav-item--active"
    >
      <span class="nav-item__icon">
        <el-icon><component :is="item.icon" /></el-icon>
      </span>
      <span class="nav-item__content">
        <span class="nav-item__label">{{ item.label }}</span>
      </span>
    </router-link>
  </el-tooltip>
</div>
```

- [ ] **Step 2: Collapse button icon direction**

Make the arrow icon flip based on state:

```vue
<button class="collapse-btn" @click="toggleSidebar" title="Toggle sidebar">
  <el-icon :size="14">
    <ArrowLeft v-if="!isCollapsed" />
    <ArrowRight v-else />
  </el-icon>
</button>
```

Add `ArrowRight` to imports:

```js
import {
  ArrowLeft,
  ArrowRight,
  FolderOpened,
  List,
  Monitor,
  Notebook,
  Setting,
} from '@element-plus/icons-vue'
```

- [ ] **Step 3: Restore collapsed state on mount**

Add to the `onMounted` function:

```js
onMounted(async () => {
  const savedTheme = localStorage.getItem('apt-workbench-theme') || 'dark'
  setTheme(savedTheme)
  // Sidebar collapse state already handled by ref initialization
  try {
    const ver = await fetchVersion()
    versionStr.value = ver.version || ''
  } catch { /* silent */ }
})
```

(The ref already handles this — `localStorage.getItem('sidebar-collapsed') === 'true'` at declaration time. This step is just a confirmation that nothing else is needed.)

- [ ] **Step 4: Brand mark centering in collapsed state**

When collapsed, the brand icon should be centered. Add:

```css
.sidebar--collapsed .brand-card {
  justify-content: center;
  padding: 8px 4px;
}

.sidebar--collapsed .collapse-btn {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
}

.sidebar--collapsed .brand-mark {
  margin: 0 auto;
}
```

Also make `.brand-card` position relative for the absolute button:

```css
.brand-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: transparent;
  border: none;
  box-shadow: none;
  position: relative;
}
```

- [ ] **Step 5: Ensure nav icons are centered with proper spacing in collapsed state**

Add collapsed-state nav-item styles:

```css
.sidebar--collapsed .nav-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.sidebar--collapsed .nav-item {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-left: 3px solid transparent;
  padding: 0;
}

.sidebar--collapsed .nav-item--active {
  border-left-color: var(--accent);
}
```

- [ ] **Step 6: Verify build**

Run:
```bash
cd frontend && npm run build
```
Expected: Build succeeds.

- [ ] **Step 7: Sync + manual test**

Sync `frontend/dist/` → `backend_v2/static/`, then start app and verify full flow:
- Arrow button toggles between left/right direction
- Collapsed: 64px width, only icons visible, centered, tooltips appear on hover
- Expanded: 240px width, full text and info visible
- Refresh page → collapse state persists
- All 3 themes (dark/light/blue) work correctly in both states
- Responsive breakpoint (<1120px) still works (sidebar becomes top bar, collapse state should reset or be ignored)

- [ ] **Step 8: Handle responsive mode**

In the responsive media query (`@media (max-width: 1120px)`), the sidebar becomes a horizontal top bar. The collapse state should not interfere. Add:

```css
@media (max-width: 1120px) {
  .app-shell--collapsed {
    grid-template-columns: 1fr !important;
  }
}
```

This ensures that on small screens, the collapse class is overridden by the existing responsive behavior.

- [ ] **Step 9: Final commit**

```bash
git add frontend/src/App.vue
git commit -m "feat: add tooltips, icon flip, and polish to sidebar collapse"
```
