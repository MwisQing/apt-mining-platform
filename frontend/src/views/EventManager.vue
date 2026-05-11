<template>
  <div class="event-manager">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">事件管理</span>
        <h2 class="page-banner__title">事件管理</h2>
        <p class="page-banner__desc">统一维护事件名称、状态、IOC、设备与跟进记录。</p>
      </div>
      <div class="page-banner__stats">
        <div class="stat-pill">
          <span>事件总数</span>
          <strong>{{ events.length }}</strong>
        </div>
        <div class="stat-pill">
          <span>活跃事件</span>
          <strong>{{ activeEventCount }}</strong>
        </div>
      </div>
    </section>

    <div class="event-layout">
      <section class="event-list-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">事件列表</div>
            <div class="panel-hint">从左侧选择事件，右侧即时编辑详情。</div>
          </div>
          <el-button type="primary" size="small" @click="handleCreateBlankEvent" class="create-btn" :loading="creatingEvent">
            <el-icon><Plus /></el-icon>
            创建事件
          </el-button>
        </div>

        <div class="status-toolbar">
          <el-button-group size="small" class="status-filter-group">
            <el-button :type="statusFilter === '' ? 'primary' : ''" @click="setStatusFilter('')">全部</el-button>
            <el-button :type="statusFilter === 'active' ? 'primary' : ''" @click="setStatusFilter('active')">活跃</el-button>
            <el-button :type="statusFilter === 'closed' ? 'primary' : ''" @click="setStatusFilter('closed')">已关闭</el-button>
          </el-button-group>
        </div>

        <div v-loading="listLoading" class="event-list">
          <div
            v-for="evt in events"
            :key="evt.id"
            class="event-card"
            :class="{ 'event-card--selected': selectedId === evt.id }"
            @click="selectEvent(evt)"
          >
            <div class="event-card__bar" :style="{ backgroundColor: evt.status === 'closed' ? '#409EFF' : (evt.color || '#409eff') }"></div>
            <div class="event-card__body">
              <div class="event-card__name">{{ evt.event_name }}</div>
              <div class="event-card__meta">
                <el-tag :type="evt.status === 'active' ? 'success' : 'info'" size="small">
                  {{ evt.status === 'active' ? '活跃' : '已关闭' }}
                </el-tag>
                <span class="event-card__time">{{ evt.mined_at }}</span>
              </div>
            </div>
          </div>

          <el-empty v-if="!listLoading && events.length === 0" description="暂无事件" :image-size="60" />
        </div>
      </section>

      <section class="event-detail-panel">
        <div v-if="!selectedEvent" class="detail-placeholder">
          <el-icon :size="48" color="var(--text-muted)"><FolderOpened /></el-icon>
          <p>从左侧选择一个事件查看详情，或新建事件开始编排。</p>
        </div>

        <template v-else>
          <div class="detail-header">
            <div class="detail-title-row">
              <div class="detail-color-dot" :style="{ backgroundColor: editColor || selectedEvent.color || '#409eff' }"></div>
              <el-input
                v-model="editName"
                size="large"
                class="title-input"
                placeholder="事件名称"
              />
            </div>
            <div class="detail-actions">
              <el-switch
                v-model="statusToggle"
                active-text="活跃"
                inactive-text="已关闭"
                :active-value="'active'"
                :inactive-value="'closed'"
                inline-prompt
                size="small"
                @change="handleStatusChange"
              />
              <el-button type="primary" size="small" @click="handleSubmit" :loading="submitting">
                <el-icon><Check /></el-icon>
                提交
              </el-button>
              <el-button size="small" @click="handleDelete">
                <el-icon><Delete /></el-icon>
                删除
              </el-button>
            </div>
          </div>

          <div class="detail-grid">
            <div class="detail-column detail-column--main">
              <div class="detail-section">
                <h4>事件颜色</h4>
                <div class="color-presets">
                  <span
                    v-for="c in presetColors"
                    :key="c"
                    class="color-preset-dot"
                    :class="{ 'color-preset--active': editColor === c }"
                    :style="{ backgroundColor: c }"
                    @click="editColor = c"
                  ></span>
                  <el-color-picker v-model="editColor" size="small" class="color-custom-picker" />
                </div>
              </div>

              <div class="detail-section">
                <h4>事件描述</h4>
                <el-input
                  v-model="editNote"
                  type="textarea"
                  :rows="14"
                  placeholder="记录事件背景、判断依据、排查过程与结论。"
                />
              </div>

              <div class="detail-section">
                <h4>跟进记录</h4>
                <div v-if="selectedEvent.followups?.length" class="timeline-wrap">
                  <el-timeline>
                    <el-timeline-item
                      v-for="(fu, idx) in selectedEvent.followups"
                      :key="idx"
                      :timestamp="fu.created_at"
                      placement="top"
                    >
                      <span class="followup-type">{{ fu.action_type }}</span>
                      <span v-if="fu.note" class="followup-note"> {{ fu.note }}</span>
                    </el-timeline-item>
                  </el-timeline>
                </div>
                <span v-else class="empty-hint">暂无跟进记录</span>

                <div class="followup-input">
                  <el-select v-model="followupType" size="small" class="followup-type-select">
                    <el-option label="跟进" value="跟进" />
                    <el-option label="备注" value="备注" />
                    <el-option label="分析" value="分析" />
                    <el-option label="结论" value="结论" />
                  </el-select>
                  <el-input v-model="followupNote" placeholder="输入跟进内容..." size="small" @keyup.enter="handleAddFollowup" />
                  <el-button type="primary" size="small" @click="handleAddFollowup" :loading="followupLoading">添加</el-button>
                </div>
              </div>
            </div>

            <div class="detail-column detail-column--side">
              <div class="detail-section side-card">
                <div class="section-title-row">
                  <h4>关联设备</h4>
                  <el-button size="small" @click="handleExtractDevices" :loading="extractLoading">识别设备 ID</el-button>
                </div>
                <el-input
                  v-model="editDevices"
                  type="textarea"
                  :rows="6"
                  placeholder="每行一个设备 ID"
                />
              </div>

              <div class="detail-section side-card">
                <div class="section-title-row">
                  <h4>关联 IOC</h4>
                  <el-button size="small" type="primary" @click="handleExtractIocs" :loading="extractLoading">识别 IOC</el-button>
                </div>
                <el-input
                  v-model="editIocs"
                  type="textarea"
                  :rows="6"
                  placeholder="每行一个 IOC，支持 target:port"
                />
              </div>
            </div>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Check, Delete, FolderOpened, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addDevices,
  addFollowup,
  addIocs,
  createEvent,
  deleteEvent,
  extractIocs,
  fetchEvent,
  fetchEvents,
  removeDevice,
  removeIoc,
  updateEvent,
} from '../api/events'

const events = ref([])
const listLoading = ref(false)
const statusFilter = ref('')
const selectedId = ref(null)
const selectedEvent = ref(null)
const creatingEvent = ref(false)
const submitting = ref(false)

const activeEventCount = computed(() => events.value.filter((evt) => evt.status === 'active').length)

function setStatusFilter(status) {
  statusFilter.value = status
  loadEvents()
}

async function loadEvents() {
  listLoading.value = true
  try {
    const params = {}
    if (statusFilter.value) params.status = statusFilter.value
    const res = await fetchEvents(params)
    events.value = res || []
  } catch (e) {
    ElMessage.error(`加载事件列表失败: ${e.message}`)
    events.value = []
  } finally {
    listLoading.value = false
  }
}

async function selectEvent(evt) {
  if (selectedId.value === evt.id) return
  selectedId.value = evt.id
  try {
    const detail = await fetchEvent(evt.id)
    selectedEvent.value = detail
    statusToggle.value = detail.status || 'active'
    editName.value = detail.event_name || ''
    editColor.value = detail.color || '#FF5722'
    editNote.value = detail.note || ''
    editDevices.value = (detail.devices || []).join('\n')
    editIocs.value = (detail.iocs || []).map((ioc) => ioc.target + (ioc.port ? ':' + ioc.port : '')).join('\n')
  } catch (e) {
    ElMessage.error(`加载事件详情失败: ${e.message}`)
  }
}

async function handleCreateBlankEvent() {
  creatingEvent.value = true
  try {
    const now = new Date()
    const pad = (n) => String(n).padStart(2, '0')
    const ts = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
    const res = await createEvent({
      event_name: `新事件 ${ts}`,
      color: '#FF5722',
      note: '',
      devices: [],
      iocs: [],
      tag_devices: false,
    })
    ElMessage.success('空白事件已创建，请在右侧填写详情')
    await loadEvents()
    const newId = res.id
    selectedId.value = newId
    const detail = await fetchEvent(newId)
    selectedEvent.value = detail
    statusToggle.value = 'active'
    editName.value = detail.event_name || ''
    editColor.value = detail.color || '#FF5722'
    editNote.value = ''
    editDevices.value = ''
    editIocs.value = ''
  } catch (e) {
    ElMessage.error(`创建事件失败: ${e.message}`)
  } finally {
    creatingEvent.value = false
  }
}

const editName = ref('')
const editColor = ref('#FF5722')
const editNote = ref('')
const editDevices = ref('')
const editIocs = ref('')
const extractLoading = ref(false)

const presetColors = [
  '#FF5722', '#E53935', '#D81B60', '#8E24AA', '#5E35B1',
  '#3949AB', '#1E88E5', '#039BE5', '#00897B', '#43A047',
  '#7CB342', '#F4511E', '#6D4C41', '#546E7A', '#455A64',
]

async function handleSubmit() {
  if (!selectedEvent.value || submitting.value) return
  submitting.value = true
  try {
    const changes = {}
    if (editName.value !== selectedEvent.value.event_name) {
      changes.event_name = editName.value
    }
    if (editColor.value !== selectedEvent.value.color) {
      changes.color = editColor.value
    }
    if (editNote.value !== selectedEvent.value.note) {
      changes.note = editNote.value
    }
    if (Object.keys(changes).length > 0) {
      await updateEvent(selectedEvent.value.id, changes)
      selectedEvent.value = { ...selectedEvent.value, ...changes }
    }

    // Save devices
    const newDevices = editDevices.value.split(/[\n\r]+/).map((s) => s.trim()).filter(Boolean)
    const currentDevices = selectedEvent.value.devices || []
    const currentSet = new Set(currentDevices.map((d) => String(d).toUpperCase()))
    for (const d of currentDevices) {
      if (!newDevices.some((nd) => nd.toUpperCase() === String(d).toUpperCase())) {
        try { await removeDevice(selectedEvent.value.id, d) } catch (e) { /* silent */ }
      }
    }
    const toAddDevices = newDevices.filter((nd) => !currentSet.has(nd.toUpperCase()))
    if (toAddDevices.length > 0) {
      await addDevices(selectedEvent.value.id, { devices: toAddDevices })
    }
    selectedEvent.value.devices = newDevices

    // Save IOCs
    const lines = editIocs.value.split(/[\n\r]+/).map((s) => s.trim()).filter(Boolean)
    const newIocs = []
    for (const line of lines) {
      const m = line.match(/^(.+?)[:：](\d{1,5})$/)
      const target = m ? m[1].trim() : line.trim()
      const port = m ? m[2] : ''
      if (target) newIocs.push({ target, port })
    }
    const currentIocs = selectedEvent.value.iocs || []
    const currentKeys = new Set(currentIocs.map((i) => `${i.target}:${i.port || ''}`))
    for (const ioc of currentIocs) {
      const key = `${ioc.target}:${ioc.port || ''}`
      if (!newIocs.some((ni) => `${ni.target}:${ni.port || ''}` === key)) {
        try { await removeIoc(selectedEvent.value.id, ioc.target, ioc.port || '') } catch (e) { /* silent */ }
      }
    }
    const toAddIocs = newIocs.filter((ni) => !currentKeys.has(`${ni.target}:${ni.port || ''}`))
    if (toAddIocs.length > 0) {
      await addIocs(selectedEvent.value.id, { iocs: toAddIocs })
    }
    selectedEvent.value.iocs = newIocs

    loadEvents()
    ElMessage.success('事件已提交并保存')
  } catch (e) {
    ElMessage.error(`提交失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    submitting.value = false
  }
}

async function handleExtractIocs() {
  const text = editNote.value
  if (!text || text.length < 3) {
    ElMessage.warning('请先在事件描述中输入文本')
    return
  }
  extractLoading.value = true
  try {
    const result = await extractIocs(text)
    if (result.iocs?.length) {
      const lines = editIocs.value.split('\n').filter(Boolean).map((l) => l.trim())
      const existing = new Set(lines)
      for (const ioc of result.iocs) {
        const line = ioc.target + (ioc.port ? ':' + ioc.port : '')
        if (!existing.has(line)) {
          lines.push(line)
          existing.add(line)
        }
      }
      editIocs.value = lines.join('\n')
      ElMessage.success(`识别到 ${result.iocs.length} 个 IOC，请点击提交按钮保存`)
    } else {
      ElMessage.info('未识别到 IOC')
    }
  } catch (e) {
    ElMessage.error(`识别 IOC 失败: ${e.message}`)
  } finally {
    extractLoading.value = false
  }
}

async function handleExtractDevices() {
  const text = editNote.value
  if (!text || text.length < 3) {
    ElMessage.warning('请先在事件描述中输入文本')
    return
  }
  extractLoading.value = true
  try {
    const result = await extractIocs(text)
    if (result.devices?.length) {
      const lines = editDevices.value.split('\n').filter(Boolean).map((l) => l.trim().toUpperCase())
      const existing = new Set(lines)
      for (const dev of result.devices) {
        if (!existing.has(dev.toUpperCase())) {
          lines.push(dev)
          existing.add(dev.toUpperCase())
        }
      }
      editDevices.value = lines.join('\n')
      ElMessage.success(`识别到 ${result.devices.length} 个设备 ID，请点击提交按钮保存`)
    } else {
      ElMessage.info('未识别到设备 ID')
    }
  } catch (e) {
    ElMessage.error(`识别设备 ID 失败: ${e.message}`)
  } finally {
    extractLoading.value = false
  }
}

const statusToggle = ref('active')

async function handleStatusChange(val) {
  if (!selectedEvent.value) return
  try {
    const payload = { status: val }
    if (val === 'closed') {
      payload.color = '#409EFF'
    } else if (val === 'active' && selectedEvent.value.color === '#409EFF') {
      payload.color = '#FF5722'
    }
    await updateEvent(selectedEvent.value.id, payload)
    selectedEvent.value.status = val
    if (payload.color) selectedEvent.value.color = payload.color
    if (val === 'closed') editColor.value = '#409EFF'
    loadEvents()
    ElMessage.success('状态已更新')
  } catch (e) {
    ElMessage.error(`更新状态失败: ${e.message}`)
  }
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm('确定要删除该事件吗？关联设备、IOC 和跟进记录也会被删除。', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  try {
    await deleteEvent(selectedEvent.value.id)
    ElMessage.success('事件已删除')
    selectedEvent.value = null
    selectedId.value = null
    loadEvents()
  } catch (e) {
    ElMessage.error(`删除失败: ${e.message}`)
  }
}

const followupType = ref('跟进')
const followupNote = ref('')
const followupLoading = ref(false)

async function handleAddFollowup() {
  if (!followupNote.value) {
    ElMessage.warning('跟进内容不能为空')
    return
  }
  followupLoading.value = true
  try {
    await addFollowup(selectedEvent.value.id, {
      action_type: followupType.value,
      note: followupNote.value,
    })
    ElMessage.success('跟进记录已添加')
    followupNote.value = ''
    const currentId = selectedEvent.value.id
    selectedId.value = null
    await selectEvent({ id: currentId })
  } catch (e) {
    ElMessage.error(`添加跟进失败: ${e.message}`)
  } finally {
    followupLoading.value = false
  }
}

onMounted(() => {
  loadEvents()
})
</script>

<style scoped>
.event-manager {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.page-banner {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px;
  border-radius: 10px;
  background: var(--panel-strong);
  border: 1px solid var(--border-strong);
  box-shadow: var(--shadow-card);
}

.page-banner__eyebrow {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.page-banner__title {
  margin: 8px 0 0;
  color: var(--text-primary);
  font-size: 24px;
}

.page-banner__desc {
  margin: 10px 0 0;
  color: var(--text-secondary);
}

.page-banner__stats {
  display: flex;
  gap: 12px;
}

.stat-pill {
  min-width: 120px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--panel-muted);
  border: 1px solid var(--border-color);
}

.stat-pill span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.stat-pill strong {
  display: block;
  margin-top: 8px;
  color: var(--text-primary);
  font-size: 18px;
}

.event-layout {
  display: flex;
  gap: 16px;
  min-height: 0;
  flex: 1;
}

.event-list-panel,
.event-detail-panel {
  background: var(--panel-strong);
  border-radius: 10px;
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-card);
}

.event-list-panel {
  width: 360px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  padding: 16px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  border-bottom: 1px solid var(--border-color);
}

.panel-title {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 700;
}

.panel-hint {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.status-toolbar {
  padding: 0 16px 12px;
}

.event-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 10px;
}

.event-card {
  display: flex;
  align-items: stretch;
  margin-bottom: 8px;
  border-radius: 8px;
  cursor: pointer;
  background: var(--panel-muted);
  border: 1px solid var(--border-color);
  transition: border-color 0.15s, background-color 0.15s, transform 0.15s;
}

.event-card:hover {
  transform: translateY(-1px);
  border-color: var(--border-strong);
  background: var(--bg-hover);
}

.event-card--selected {
  border-color: rgba(91, 169, 255, 0.34);
  background: var(--accent-light);
}

.event-card__bar {
  width: 4px;
  border-radius: 8px 0 0 8px;
  flex-shrink: 0;
}

.event-card__body {
  flex: 1;
  padding: 12px 14px;
  min-width: 0;
}

.event-card__name {
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 6px;
}

.event-card__meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.event-card__time {
  font-size: 12px;
  color: var(--text-muted);
}

.event-detail-panel {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.detail-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
}

.detail-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-color);
}

.detail-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.detail-color-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  flex-shrink: 0;
}

.title-input {
  font-size: 20px;
  font-weight: 700;
}

.detail-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 18px;
}

.detail-column {
  min-width: 0;
}

.detail-section {
  margin-bottom: 18px;
  padding: 14px;
  border-radius: 8px;
  background: var(--panel-muted);
  border: 1px solid var(--border-color);
}

.detail-section h4 {
  margin: 0 0 12px;
  color: var(--text-primary);
  font-size: 14px;
}

.section-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.section-title-row h4 {
  margin: 0;
}

.empty-hint,
.followup-note {
  color: var(--text-secondary);
}

.followup-type {
  color: var(--text-primary);
  font-weight: 700;
}

.followup-input {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.followup-type-select {
  width: 90px;
}

.color-presets {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.color-preset-dot {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: transform 0.15s, border-color 0.15s;
}

.color-preset-dot:hover {
  transform: scale(1.08);
}

.color-preset--active {
  border-color: #fff;
  box-shadow: 0 0 0 2px var(--accent);
}

.timeline-wrap {
  margin-bottom: 12px;
}

@media (max-width: 1080px) {
  .event-layout,
  .detail-grid,
  .page-banner {
    flex-direction: column;
    display: flex;
  }

  .event-list-panel {
    width: 100%;
  }
}

@media (max-width: 720px) {
  .detail-header,
  .followup-input,
  .section-title-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
