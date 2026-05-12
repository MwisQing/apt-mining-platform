import { computed, ref } from 'vue'

const STORAGE_KEY_PREFIX = 'apt-workbench-columns'

let _jsonColumnsCache = null

const FALLBACK_COLUMNS = {
  workbench: [
    { key: 'priority', label: '优先级', width: 80, visible: true },
    { key: 'score', label: '分数', width: 65, visible: true },
    { key: 'device_id', label: '设备ID', width: 160, visible: true },
    { key: 'device_tags', label: '设备标签', width: 150, visible: true },
    { key: 'device_target_count', label: '设备告警ioc数', width: 110, visible: true },
    { key: 'source_ip', label: '源IP', width: 130, visible: true },
    { key: 'source_ip_count', label: '源IP数', width: 75, visible: true },
    { key: 'target', label: '外联目标', width: 180, visible: true },
    { key: 'alert_count', label: '告警次数', width: 90, visible: true },
    { key: 'port', label: '端口', width: 70, visible: true },
    { key: 'device_alert_count', label: '外联告警数量', width: 110, visible: true },
    { key: 'ioc_note', label: 'IOC备注', width: 200, visible: true },
    { key: 'event', label: '事件', width: 120, visible: true },
    { key: 'threat_type', label: '威胁类型', width: 100, visible: true },
    { key: 'std_apt_org', label: 'APT组织', width: 130, visible: true },
    { key: 'analysis_status', label: '研判状态', width: 100, visible: true },
    { key: 'heat', label: '外联目标热度', width: 110, visible: true },
    { key: 'is_focused', label: '重点关注', width: 90, visible: false },
    { key: 'candidate_reasons', label: '命中原因', width: 200, visible: false },
    { key: 'badges', label: '徽章', width: 180, visible: false },
  ],
}

async function loadJsonColumns() {
  if (_jsonColumnsCache) return _jsonColumnsCache
  try {
    const resp = await fetch('/columns.json')
    if (resp.ok) {
      _jsonColumnsCache = await resp.json()
    }
  } catch (e) { /* ignore */ }
  return _jsonColumnsCache || {}
}

function loadLocalOverrides(pageKey) {
  const storageKey = `${STORAGE_KEY_PREFIX}-${pageKey}`
  try {
    // Migrate from old key format
    if (pageKey === 'workbench') {
      const oldKey = 'apt-workbench-columns'
      const oldData = localStorage.getItem(oldKey)
      if (oldData && !localStorage.getItem(storageKey)) {
        localStorage.setItem(storageKey, oldData)
        localStorage.removeItem(oldKey)
      }
    }
    const saved = localStorage.getItem(storageKey)
    if (saved) return JSON.parse(saved)
  } catch (e) { /* ignore */ }
  return null
}

function mergeColumns(jsonDefaults, localOverrides) {
  if (!jsonDefaults || jsonDefaults.length === 0) return []
  if (!localOverrides || localOverrides.length === 0) {
    return jsonDefaults.map(c => ({ ...c }))
  }

  const overrideMap = {}
  for (const c of localOverrides) {
    overrideMap[c.key] = c
  }

  // Start with JSON defaults, apply local overrides for width/visible
  const merged = []
  const seenKeys = new Set()
  for (const def of jsonDefaults) {
    const ov = overrideMap[def.key]
    if (ov) {
      merged.push({ ...def, width: ov.width ?? def.width, visible: ov.visible ?? def.visible })
    } else {
      merged.push({ ...def })
    }
    seenKeys.add(def.key)
  }

  // Append any local-only columns not in JSON (user added before JSON existed)
  for (const c of localOverrides) {
    if (!seenKeys.has(c.key)) {
      merged.push({ ...c })
    }
  }

  return merged
}

/**
 * Initialize column configs from columns.json.
 * Must be awaited before using useColumnConfig().
 */
export async function initColumnConfig() {
  await loadJsonColumns()
}

export function useColumnConfig(pageKey = 'workbench') {
  const storageKey = `${STORAGE_KEY_PREFIX}-${pageKey}`

  const jsonDefaults = (_jsonColumnsCache && _jsonColumnsCache[pageKey]) || FALLBACK_COLUMNS[pageKey] || []
  const localOverrides = loadLocalOverrides(pageKey)
  const initialColumns = mergeColumns(jsonDefaults, localOverrides)

  const columns = ref(initialColumns)
  const resizing = ref(null)
  const savedSnapshot = ref(JSON.stringify(columns.value.map(c => ({ key: c.key, width: c.width, visible: c.visible }))))

  const visibleColumns = () => columns.value.filter(c => c.visible)
  const allColumns = () => columns.value
  const hasPendingChanges = computed(() => {
    const current = JSON.stringify(columns.value.map(c => ({ key: c.key, width: c.width, visible: c.visible })))
    return current !== savedSnapshot.value
  })

  function toggleColumn(key) {
    const col = columns.value.find(c => c.key === key)
    if (col) {
      col.visible = !col.visible
    }
  }

  function persistColumns() {
    const toSave = columns.value.map(c => ({ key: c.key, width: c.width, visible: c.visible }))
    localStorage.setItem(storageKey, JSON.stringify(toSave))
    savedSnapshot.value = JSON.stringify(toSave)
  }

  function resetColumns() {
    const fresh = jsonDefaults.map(c => ({ ...c }))
    columns.value = fresh
    localStorage.removeItem(storageKey)
    savedSnapshot.value = JSON.stringify(fresh.map(c => ({ key: c.key, width: c.width, visible: c.visible })))
  }

  function onResizeStart(key, event) {
    event.preventDefault()
    event.stopPropagation()
    resizing.value = {
      key,
      startX: event.clientX,
      startWidth: columns.value.find(c => c.key === key)?.width || 100,
    }
    document.addEventListener('mousemove', onResizeMove)
    document.addEventListener('mouseup', onResizeEnd)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  function onResizeMove(event) {
    if (!resizing.value) return
    const diff = event.clientX - resizing.value.startX
    const newWidth = Math.max(50, Math.min(600, resizing.value.startWidth + diff))
    const col = columns.value.find(c => c.key === resizing.value.key)
    if (col) col.width = newWidth
  }

  function onResizeEnd() {
    if (resizing.value) {
      resizing.value = null
    }
    document.removeEventListener('mousemove', onResizeMove)
    document.removeEventListener('mouseup', onResizeEnd)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }

  const isResizing = computed(() => resizing.value !== null)

  return {
    columns,
    visibleColumns,
    allColumns,
    toggleColumn,
    persistColumns,
    resetColumns,
    hasPendingChanges,
    onResizeStart,
    resizing,
    isResizing,
  }
}

export function saveColumnOrder(columns, pageKey = 'workbench') {
  const storageKey = `${STORAGE_KEY_PREFIX}-${pageKey}`
  const toSave = columns.map(c => ({ key: c.key, width: c.width, visible: c.visible }))
  localStorage.setItem(storageKey, JSON.stringify(toSave))
}
