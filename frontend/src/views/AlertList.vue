<template>
  <div class="alerts-page">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">原始告警</span>
        <h2 class="page-banner__title">原始告警检索</h2>
        <p class="page-banner__desc">直接查看底层告警明细，交叉验证候选结果和命中依据。</p>
      </div>
      <div class="page-banner__stats">
        <div class="stat-pill">
          <span>告警总数</span>
          <strong>{{ total }}</strong>
        </div>
        <div class="stat-pill">
          <span>已选威胁类型</span>
          <strong>{{ threatTypes.length || '全部' }}</strong>
        </div>
      </div>
    </section>

    <section class="filter-bar">
      <div class="filter-bar__intro">
        <div>
          <div class="filter-bar__title">告警筛选</div>
          <div class="filter-bar__hint">支持目标类型、威胁类型、标签与关键字组合筛选。</div>
        </div>
        <div class="filter-actions">
          <el-button size="small" @click="loadData">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
          <el-button size="small" @click="handleExportCsv">
            <el-icon><Download /></el-icon>
            导出
          </el-button>
        </div>
      </div>

      <div class="filter-row">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY年MM月DD日"
          value-format="YYYY-MM-DD"
          size="small"
          class="filter-item date-picker"
        />

        <el-select
          v-model="targetType"
          placeholder="目标类型"
          size="small"
          clearable
          class="filter-item target-type-select"
          @change="handleSearch"
        >
          <el-option v-for="opt in options.target_types" :key="opt" :label="opt" :value="opt" />
        </el-select>

        <el-select
          v-model="threatTypes"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="威胁类型"
          size="small"
          class="filter-item threat-type-select"
          @change="handleSearch"
        >
          <el-option v-for="opt in options.threat_types" :key="opt" :label="opt" :value="opt" />
        </el-select>

        <el-select
          v-model="threatLevels"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="威胁等级"
          size="small"
          class="filter-item threat-level-select"
          @change="handleSearch"
        >
          <el-option v-for="opt in options.threat_levels" :key="opt" :label="opt" :value="opt" />
        </el-select>

        <el-select
          v-model="deviceTagIds"
          multiple
          collapse-tags
          collapse-tags-tooltip
          placeholder="设备标签"
          size="small"
          class="filter-item device-tag-select"
          @change="handleSearch"
        >
          <el-option v-for="tag in options.device_tags" :key="tag.id" :label="tag.name" :value="tag.id" />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="关键字搜索"
          size="small"
          clearable
          class="filter-item keyword-input"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <div class="filter-item switch-group">
          <span class="switch-label">隐藏已追踪</span>
          <el-switch v-model="hideTraced" size="small" @change="handleSearch" />
        </div>

        <el-button type="primary" size="small" @click="handleSearch" class="filter-item">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </div>
    </section>

    <section class="table-card">
      <div class="table-card__header">
        <div>
          <div class="table-card__title">原始告警明细</div>
          <div class="table-card__hint">默认按设备、目标、IOC 备注与事件归属进行阅读布局。</div>
        </div>
        <span class="table-chip">{{ pageSize }} / 页</span>
      </div>

      <el-table
        :data="tableData"
        size="small"
        v-loading="loading"
        stripe
        row-key="id"
        class="alerts-table"
        :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
      >
        <el-table-column label="设备ID" min-width="120" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">设备ID</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="device_id" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            <span class="device-id">{{ row.device_id }}</span>
          </template>
        </el-table-column>

        <el-table-column label="首次告警时间" width="165" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">首次告警时间</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="first_alert_time" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            <span class="time-cell">{{ row.first_alert_time || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="最近告警时间" width="165" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">最近告警时间</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="last_alert_time" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            <span class="time-cell">{{ row.last_alert_time || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="源IP" width="130" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">源IP</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="source_ip" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            <span class="source-ip">{{ row.source_ip || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="外联目标" min-width="180" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">外联目标</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="target" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            <span class="target-cell">{{ row.target }}</span>
          </template>
        </el-table-column>

        <el-table-column label="外联端口" width="80" align="center">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">外联端口</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="port" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            {{ row.port || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="威胁类型" width="100">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">威胁类型</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="threat_type" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            <el-tag :type="threatTypeTag(row.threat_type)" size="small">
              {{ row.threat_type || '-' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="威胁等级" width="80" align="center">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">威胁等级</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="threat_level" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            {{ row.threat_level || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="标准APT组织" width="120" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">标准APT组织</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="std_apt_org" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            {{ row.std_apt_org || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="APT组织" width="100" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">APT组织</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="apt_org" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            {{ row.apt_org || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="APT组织分类" width="100" align="center">
          <template #default="{ row }">
            {{ row.apt_org_tier || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="告警次数" width="80" align="center">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">告警次数</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="alert_count" @sort="handleSortClick" />
            </div>
          </template>
          <template #default="{ row }">
            <span class="count-cell">{{ row.alert_count || 0 }}</span>
          </template>
        </el-table-column>

        <el-table-column label="厂商" width="100" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.vendors || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="协议" width="70" align="center">
          <template #default="{ row }">
            {{ row.protocol || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="情报标签" width="100" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.intel_tags || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="目标类型" width="90" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.target_type || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="情报位置" width="90" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.intel_position || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="处置动作" width="90" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.disposal_action || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="DNS解析IP" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="source-ip">{{ row.dns_resolved_ip || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="下行流量" width="90" align="center">
          <template #default="{ row }">
            {{ row.down_traffic != null ? formatTraffic(row.down_traffic) : '-' }}
          </template>
        </el-table-column>

        <el-table-column label="上行流量" width="90" align="center">
          <template #default="{ row }">
            {{ row.up_traffic != null ? formatTraffic(row.up_traffic) : '-' }}
          </template>
        </el-table-column>

        <el-table-column label="资产类型" width="90" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.asset_type || '-' }}
          </template>
        </el-table-column>

        <el-table-column label="研判状态" width="90" align="center">
          <template #default="{ row }">
            <span class="empty-cell">{{ row.analysis_status || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="重点关注" width="80" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.is_focused" color="#F56C6C" :size="16"><StarFilled /></el-icon>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[50, 100, 200, 500]"
          layout="total, sizes, prev, pager, next"
          background
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { CaretTop, CaretBottom, Download, RefreshRight, Search, StarFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { exportAlerts, fetchAlertOptions, fetchAlerts } from '../api/alerts'
import { fetchConfig } from '../api/config'

const options = ref({
  target_types: [],
  threat_types: [],
  threat_levels: [],
  device_tags: [],
})

const sortField = ref('')
const sortOrder = ref('')

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

function handleSortClick(key) {
  if (sortField.value === key) {
    if (sortOrder.value === 'desc') {
      sortOrder.value = 'asc'
    } else {
      sortField.value = ''
      sortOrder.value = ''
    }
  } else {
    sortField.value = key
    sortOrder.value = 'desc'
  }
  currentPage.value = 1
  loadData()
}

const dateRange = ref(null)
const targetType = ref('')
const threatTypes = ref([])
const threatLevels = ref([])
const deviceTagIds = ref([])
const keyword = ref('')
const hideTraced = ref(true)

const tableData = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(100)
const total = ref(0)

async function loadOptions() {
  try {
    const res = await fetchAlertOptions()
    options.value = {
      target_types: res.target_types || [],
      threat_types: res.threat_types || [],
      threat_levels: res.threat_levels || [],
      device_tags: res.device_tags || [],
    }
  } catch (e) {
    /* ignore */
  }
}

async function loadData() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      hide_traced: hideTraced.value,
    }

    if (dateRange.value && dateRange.value.length === 2) {
      params.date_start = dateRange.value[0]
      params.date_end = dateRange.value[1]
    }
    if (targetType.value) params.target_type = targetType.value
    if (threatTypes.value.length > 0) params.threat_types = threatTypes.value.join(',')
    if (threatLevels.value.length > 0) params.threat_levels = threatLevels.value.join(',')
    if (deviceTagIds.value.length > 0) params.device_tags = deviceTagIds.value.join(',')
    if (keyword.value) params.keyword = keyword.value
    if (sortField.value) {
      params.sort_by = sortField.value
      params.sort_order = sortOrder.value
    }

    const res = await fetchAlerts(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error(`加载告警数据失败: ${e.message}`)
    tableData.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  keyword.value = keyword.value.trim()
  currentPage.value = 1
  loadData()
}

async function handleExportCsv() {
  const params = { hide_traced: hideTraced.value }
  if (dateRange.value && dateRange.value.length === 2) {
    params.date_start = dateRange.value[0]
    params.date_end = dateRange.value[1]
  }
  if (targetType.value) params.target_type = targetType.value
  if (threatTypes.value.length > 0) params.threat_types = threatTypes.value.join(',')
  if (threatLevels.value.length > 0) params.threat_levels = threatLevels.value.join(',')
  if (deviceTagIds.value.length > 0) params.device_tags = deviceTagIds.value.join(',')
  if (keyword.value) params.keyword = keyword.value

  try {
    await exportAlerts(params)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error(`导出失败: ${e.message}`)
  }
}

function threatTypeTag(type) {
  if (!type) return 'info'
  const lower = type.toLowerCase()
  if (lower.includes('apt')) return 'danger'
  if (lower.includes('远控') || lower.includes('remote')) return 'warning'
  return 'info'
}

function formatTraffic(val) {
  if (val == null || val === 0) return '0'
  if (val >= 1073741824) return (val / 1073741824).toFixed(1) + ' GB'
  if (val >= 1048576) return (val / 1048576).toFixed(1) + ' MB'
  if (val >= 1024) return (val / 1024).toFixed(1) + ' KB'
  return val + ' B'
}

async function loadConfigInit() {
  try {
    const cfg = await fetchConfig()
    if (cfg.default_hide_traced !== undefined) {
      hideTraced.value = !!cfg.default_hide_traced
    }
  } catch (e) {
    /* ignore */
  }
}

onMounted(async () => {
  await Promise.all([loadOptions(), loadConfigInit()])
  loadData()
})
</script>

<style scoped>
.alerts-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.page-banner,
.filter-bar,
.table-card {
  border-radius: 10px;
  background: var(--panel-strong);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-card);
}

.page-banner {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px;
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
  min-width: 130px;
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

.filter-bar {
  padding: 16px 18px;
}

.filter-bar__intro,
.table-card__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.filter-bar__intro {
  margin-bottom: 14px;
}

.filter-bar__title,
.table-card__title {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 700;
}

.filter-bar__hint,
.table-card__hint {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.filter-actions {
  display: flex;
  gap: 8px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-item {
  flex-shrink: 0;
}

.date-picker {
  width: 280px;
}

.target-type-select {
  width: 130px;
}

.threat-type-select {
  width: 150px;
}

.threat-level-select {
  width: 140px;
}

.device-tag-select {
  width: 160px;
}

.keyword-input {
  width: 180px;
}

.switch-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.switch-label {
  font-size: 13px;
  color: var(--switch-label);
  white-space: nowrap;
}

.table-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 16px 18px 12px;
}

.table-chip {
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.alerts-table {
  flex: 1;
  margin-top: 14px;
}

.alerts-table :deep(.el-table__body-wrapper) {
  background-color: var(--table-row-bg);
}

.alerts-table :deep(.el-table__body tr) {
  background-color: var(--table-row-bg);
}

.alerts-table :deep(.el-table__body tr:hover > td) {
  background-color: var(--table-row-hover) !important;
}

.alerts-table :deep(.el-table__body tr.el-table__row--striped td) {
  background-color: var(--table-row-stripe);
}

.device-id,
.source-ip {
  font-family: "Consolas", monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.target-cell,
.count-cell {
  color: var(--text-primary);
}

.count-cell {
  font-weight: 700;
}

.heat-cell,
.note-cell,
.time-cell {
  color: var(--text-secondary);
  font-size: 12px;
}

.empty-cell {
  color: var(--text-muted);
}

.resizable-header {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
}

.col-label-text {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

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
  margin-left: 4px;
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

.pagination-bar {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  padding: 8px 0;
}

@media (max-width: 1080px) {
  .page-banner,
  .page-banner__stats {
    flex-direction: column;
  }
}

@media (max-width: 720px) {
  .filter-bar__intro,
  .table-card__header,
  .filter-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
