import { computed, ref } from 'vue'

const STORAGE_KEY = 'apt-workbench-columns'

const DEFAULT_COLUMNS = [
  { key: 'priority', label: '优先级', width: 80, visible: true, sortable: false },
  { key: 'score', label: '分数', width: 65, visible: true, sortable: true },
  { key: 'device_id', label: '设备ID', width: 130, visible: true, sortable: true },
  { key: 'device_tags', label: '设备标签', width: 150, visible: true, sortable: false },
  { key: 'device_target_count', label: '设备告警ioc数', width: 110, visible: true, sortable: true },
  { key: 'source_ip', label: '源IP', width: 130, visible: true, sortable: true },
  { key: 'source_ip_count', label: '源IP数', width: 75, visible: true, sortable: true },
  { key: 'target', label: '外联目标', width: 180, visible: true, sortable: true },
  { key: 'port', label: '端口', width: 70, visible: true, sortable: true },
  { key: 'device_alert_count', label: '外联告警数量', width: 110, visible: true, sortable: true },
  { key: 'ioc_note', label: 'IOC备注', width: 200, visible: true, sortable: false },
  { key: 'event', label: '事件', width: 120, visible: true, sortable: false },
  { key: 'threat_type', label: '威胁类型', width: 90, visible: true, sortable: true },
  { key: 'std_apt_org', label: 'APT组织', width: 130, visible: true, sortable: true },
  { key: 'analysis_status', label: '研判状态', width: 100, visible: true, sortable: true },
  { key: 'heat', label: '外联目标热度', width: 110, visible: true, sortable: true },
  { key: 'is_focused', label: '重点关注', width: 90, visible: false, sortable: true },
  { key: 'candidate_reasons', label: '命中原因', width: 200, visible: false, sortable: false },
  { key: 'badges', label: '徽章', width: 180, visible: false, sortable: false },
]

function loadConfig() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      // Respect saved order: build array from saved keys, merge defaults for missing
      const savedKeys = parsed.map(c => c.key)
      const defaultMap = {}
      for (const col of DEFAULT_COLUMNS) {
        defaultMap[col.key] = col
      }
      const merged = []
      for (const saved of parsed) {
        const def = defaultMap[saved.key]
        if (def) {
          merged.push({ ...def, width: saved.width || def.width, visible: saved.visible !== false })
        }
      }
      // Append any defaults not in saved
      for (const col of DEFAULT_COLUMNS) {
        if (!savedKeys.includes(col.key)) {
          merged.push({ ...col })
        }
      }
      return merged
    }
  } catch (e) { /* ignore */ }
  return DEFAULT_COLUMNS.map(c => ({ ...c }))
}

function saveConfig(columns) {
  const toSave = columns.map(c => ({ key: c.key, width: c.width, visible: c.visible }))
  localStorage.setItem(STORAGE_KEY, JSON.stringify(toSave))
}

export function saveColumnOrder(columns) {
  saveConfig(columns)
}

export function useColumnConfig() {
  const columns = ref(loadConfig())
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
    saveConfig(columns.value)
    savedSnapshot.value = JSON.stringify(columns.value.map(c => ({ key: c.key, width: c.width, visible: c.visible })))
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
    hasPendingChanges,
    onResizeStart,
    resizing,
    isResizing,
  }
}
