<template>
  <div class="annotation-page">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">告警标注</span>
        <h2 class="page-banner__title">人工标注</h2>
        <p class="page-banner__desc">对单条告警设置分析状态、重点关注状态和备注。</p>
      </div>
    </section>

    <section class="filter-bar">
      <div class="filter-bar__intro">
        <div>
          <div class="filter-bar__title">告警筛选</div>
          <div class="filter-bar__hint">按日期、威胁类型和关键词筛选。</div>
        </div>
        <el-button size="small" @click="loadData">
          <el-icon><RefreshRight /></el-icon>
          刷新
        </el-button>
      </div>

      <div class="filter-row">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          size="small"
          class="filter-item"
        />

        <el-select
          v-model="threatType"
          placeholder="威胁类型"
          size="small"
          clearable
          class="filter-item"
          @change="loadData"
        >
          <el-option v-for="opt in threatTypes" :key="opt" :label="opt" :value="opt" />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="关键字搜索"
          size="small"
          clearable
          class="filter-item"
          @keyup.enter="loadData"
          @clear="loadData"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>

        <el-button type="primary" size="small" @click="loadData">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </div>
    </section>

    <section class="table-card">
      <el-table :data="tableData" size="small" v-loading="loading" stripe row-key="id">
        <el-table-column label="ID" width="60">
          <template #default="{ row }">{{ row.id }}</template>
        </el-table-column>

        <el-table-column label="设备ID" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.device_id }}</template>
        </el-table-column>

        <el-table-column label="源IP" width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.source_ip || '-' }}</template>
        </el-table-column>

        <el-table-column label="外联目标" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target }}</template>
        </el-table-column>

        <el-table-column label="威胁类型" width="100">
          <template #default="{ row }">
            <el-tag :type="threatTypeTag(row.threat_type)" size="small">{{ row.threat_type || '-' }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="威胁等级" width="80" align="center">
          <template #default="{ row }">{{ row.threat_level || '-' }}</template>
        </el-table-column>

        <el-table-column label="分析状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="analysisStatusType(row.analysis_status)" size="small">
              {{ row.analysis_status || '未分析' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="重点关注" width="80" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.is_focused" color="#F56C6C" :size="16"><StarFilled /></el-icon>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>

        <el-table-column label="首次告警" width="165">
          <template #default="{ row }">{{ row.first_alert_time || '-' }}</template>
        </el-table-column>

        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="openAnnotate(row)">标注</el-button>
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

    <el-dialog v-model="dialogVisible" title="告警标注" width="420px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="分析状态">
          <el-select v-model="form.analysis_status" placeholder="选择分析状态" style="width: 100%">
            <el-option label="未分析" value="" />
            <el-option label="分析中" value="分析中" />
            <el-option label="已完成" value="已完成" />
          </el-select>
        </el-form-item>
        <el-form-item label="重点关注">
          <el-switch v-model="form.is_focused" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveAnnotation" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RefreshRight, Search, StarFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { annotateAlert, fetchAlerts, fetchAlertOptions } from '../api/alerts'

const threatTypes = ref([])
const dateRange = ref(null)
const threatType = ref('')
const keyword = ref('')

const tableData = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)

const dialogVisible = ref(false)
const saving = ref(false)
const form = ref({ id: null, analysis_status: '', is_focused: false })

async function loadOptions() {
  try {
    const res = await fetchAlertOptions()
    threatTypes.value = res.threat_types || []
  } catch { /* ignore */ }
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    if (dateRange.value?.length === 2) {
      params.date_start = dateRange.value[0]
      params.date_end = dateRange.value[1]
    }
    if (threatType.value) params.threat_types = threatType.value
    if (keyword.value) params.keyword = keyword.value

    const res = await fetchAlerts(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error(`加载告警失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

function openAnnotate(row) {
  form.value = { id: row.id, analysis_status: row.analysis_status || '', is_focused: !!row.is_focused }
  dialogVisible.value = true
}

async function saveAnnotation() {
  saving.value = true
  try {
    await annotateAlert(form.value.id, {
      analysis_status: form.value.analysis_status,
      is_focused: form.value.is_focused,
    })
    ElMessage.success('标注已保存')
    dialogVisible.value = false
    loadData()
  } catch (e) {
    ElMessage.error(`保存失败: ${e.message}`)
  } finally {
    saving.value = false
  }
}

function threatTypeTag(type) {
  if (!type) return 'info'
  const lower = type.toLowerCase()
  if (lower.includes('apt')) return 'danger'
  if (lower.includes('远控') || lower.includes('remote')) return 'warning'
  return 'info'
}

function analysisStatusType(status) {
  if (!status || status === '') return 'info'
  if (status === '分析中') return 'warning'
  if (status === '已完成') return 'success'
  return 'info'
}

onMounted(() => { loadOptions(); loadData() })
</script>

<style scoped>
.annotation-page { display: flex; flex-direction: column; gap: 18px; }
.page-banner { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 16px 0; }
.page-banner__eyebrow { color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
.page-banner__title { margin: 4px 0 0; font-size: 22px; font-weight: 700; }
.page-banner__desc { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.filter-bar { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.filter-bar__intro { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 12px; }
.filter-bar__title { font-size: 13px; font-weight: 600; }
.filter-bar__hint { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { min-width: 140px; }
.table-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.pagination-bar { display: flex; justify-content: center; margin-top: 16px; }
.empty-cell { color: var(--text-muted); }
</style>
