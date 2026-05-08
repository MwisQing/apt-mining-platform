<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-card">
        <div class="brand-mark">
          <el-icon :size="18"><Monitor /></el-icon>
        </div>
        <div class="brand-copy">
          <div class="brand-title">APT Mining</div>
          <div class="brand-subtitle">Workbench</div>
        </div>
      </div>

      <div class="nav-section">
        <div class="section-label">导航</div>
        <button
          v-for="item in navItems"
          :key="item.path"
          class="nav-item"
          :class="{ 'nav-item--active': route.path === item.path }"
          @click="navigate(item.path)"
        >
          <span class="nav-item__icon">
            <el-icon><component :is="item.icon" /></el-icon>
          </span>
          <span class="nav-item__content">
            <span class="nav-item__label">{{ item.label }}</span>
            <span class="nav-item__hint">{{ item.hint }}</span>
          </span>
        </button>
      </div>

      <div class="sidebar-footer">
        <div class="footer-row">
          <div class="theme-dots">
            <button
              v-for="theme in themeOptions"
              :key="theme.value"
              class="theme-dot-btn"
              :class="{ active: currentTheme === theme.value }"
              :title="theme.label"
              @click="setTheme(theme.value)"
            >
              <span class="dot" :class="theme.dotClass"></span>
            </button>
          </div>
          <span class="footer-end">127.0.0.1:8088</span>
        </div>
      </div>
    </aside>

    <section class="main-shell">
      <header v-if="hasTopbarCopy" class="topbar">
        <div class="topbar-copy">
          <template v-if="currentPage.kicker || currentPage.title || currentPage.subtitle">
            <p v-if="currentPage.kicker" class="topbar-kicker">{{ currentPage.kicker }}</p>
            <h1 v-if="currentPage.title" class="topbar-title">{{ currentPage.title }}</h1>
            <p v-if="currentPage.subtitle" class="topbar-subtitle">{{ currentPage.subtitle }}</p>
          </template>
        </div>
      </header>

      <main class="content-pane">
        <transition name="page-fade" mode="out-in">
          <router-view />
        </transition>
      </main>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  FolderOpened,
  List,
  Monitor,
  Notebook,
  Setting,
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const currentTheme = ref('dark')

const navItems = [
  { path: '/', label: '研判工作台', hint: '候选事件与优先级', icon: Monitor },
  { path: '/events', label: '事件管理', hint: '事件编排与跟进', icon: FolderOpened },
  { path: '/ioc-notes', label: 'IOC 备注', hint: '追踪目标与注释', icon: Notebook },
  { path: '/settings', label: '导入与设置', hint: '导入、标签与系统配置', icon: Setting },
  { path: '/alerts', label: '原始告警', hint: '完整告警检索视图', icon: List },
]

const pageMeta = {
  '/': {
    kicker: '',
    title: '',
    subtitle: '',
  },
  '/events': {
    kicker: '',
    title: '事件管理',
    subtitle: '维护事件详情、关联设备与 IOC，并持续沉淀跟进记录。',
  },
  '/ioc-notes': {
    kicker: '',
    title: 'IOC 备注',
    subtitle: '集中维护追踪目标备注，方便跨批次继承历史判断。',
  },
  '/settings': {
    kicker: '',
    title: '导入与设置',
    subtitle: '处理告警导入、标签批次、追踪库和系统配置。',
  },
  '/alerts': {
    kicker: '',
    title: '原始告警',
    subtitle: '查看完整原始告警明细，验证候选结果与底层数据来源。',
  },
}

const themeOptions = [
  { value: 'dark', label: '暗色主题', shortLabel: '暗色', dotClass: 'dot-dark' },
  { value: 'vscode-light', label: '浅色主题', shortLabel: '浅色', dotClass: 'dot-light' },
  { value: 'vs2026', label: '蓝灰主题', shortLabel: '蓝灰', dotClass: 'dot-blue' },
]

const currentPage = computed(() => pageMeta[route.path] || pageMeta['/'])
const TOPBAR_HIDDEN_ROUTES = new Set(['/events', '/ioc-notes', '/settings', '/alerts'])
const hasTopbarCopy = computed(() => {
  if (TOPBAR_HIDDEN_ROUTES.has(route.path)) return false
  return Boolean(currentPage.value.kicker || currentPage.value.title || currentPage.value.subtitle)
})
function navigate(path) {
  if (route.path !== path) {
    router.push(path)
  }
}

function setTheme(theme) {
  currentTheme.value = theme
  document.documentElement.setAttribute('data-theme', theme)
  localStorage.setItem('apt-workbench-theme', theme)
}

onMounted(() => {
  const savedTheme = localStorage.getItem('apt-workbench-theme') || 'dark'
  setTheme(savedTheme)
})
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  background: var(--bg-primary);
}

.sidebar {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 20px 14px 14px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border-strong);
}

.brand-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: transparent;
  border: none;
  box-shadow: none;
}

.brand-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: var(--text-inverse);
  background: linear-gradient(135deg, var(--accent), var(--accent-strong));
  box-shadow: 0 6px 14px rgba(44, 120, 255, 0.22);
  flex-shrink: 0;
}

.brand-copy {
  min-width: 0;
}

.brand-title {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.brand-subtitle {
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.3;
}

.nav-section {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-label {
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  padding: 0 6px;
}

.nav-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  border-left: 3px solid transparent;
  background: transparent;
  color: var(--sidebar-text);
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
}

.nav-item:hover {
  border-color: var(--border-strong);
  background: var(--sidebar-active);
  color: var(--sidebar-active-text);
}

.nav-item--active {
  border-color: var(--border-strong);
  border-left-color: var(--accent);
  background: var(--sidebar-active);
  color: var(--sidebar-active-text);
  box-shadow: none;
}

.nav-item__icon {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 4px;
  flex-shrink: 0;
  color: inherit;
  background: transparent;
}

.nav-item--active .nav-item__icon {
  background: transparent;
  color: var(--accent);
}

.nav-item__content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.nav-item__label {
  color: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.2;
}

.nav-item__hint {
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.3;
}

.sidebar-footer {
  position: relative;
  z-index: 1;
  margin-top: auto;
}

.footer-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 0 0;
  border-top: 1px solid var(--border-color);
}

.theme-dots {
  display: flex;
  gap: 6px;
}

.theme-dot-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 2px solid transparent;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: border-color 0.15s ease, transform 0.15s ease;
  background: transparent;
}

.theme-dot-btn:hover {
  transform: scale(1.1);
}

.theme-dot-btn.active {
  border-color: var(--accent);
}

.theme-dot-btn .dot {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  flex-shrink: 0;
}

.dot-dark {
  background: #0d1829;
}
.dot-light {
  background: #fbfdff;
}
.dot-blue {
  background: #f5f8fc;
}

.footer-end {
  flex: 1;
  text-align: right;
  color: var(--text-muted);
  font-size: 10px;
}

.main-shell {
  min-width: 0;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 24px 28px 18px;
}

.topbar-kicker {
  margin: 0 0 6px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.topbar-title {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(24px, 2vw, 32px);
  font-weight: 700;
  letter-spacing: -0.02em;
}

.topbar-subtitle {
  max-width: 760px;
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
}

.content-pane {
  flex: 1;
  min-height: 0;
  padding: 0 28px 28px;
  overflow: auto;
}

@media (max-width: 1120px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    gap: 18px;
    padding-bottom: 22px;
    border-right: none;
    border-bottom: 1px solid var(--border-strong);
  }

  .nav-section {
    overflow-x: auto;
  }

  .nav-item {
    min-width: 220px;
  }
}

@media (max-width: 720px) {
  .sidebar {
    padding: 18px 14px 16px;
  }

  .brand-card {
    padding: 14px;
  }

  .topbar {
    padding: 18px 16px 14px;
    flex-direction: column;
  }

  .content-pane {
    padding: 0 16px 18px;
  }
}
</style>
