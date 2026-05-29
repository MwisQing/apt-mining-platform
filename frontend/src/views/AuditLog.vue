<template>
  <div class="audit-page">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">审计日志</span>
        <h2 class="page-banner__title">操作记录</h2>
        <p class="page-banner__desc">查看系统操作历史：谁在何时做了什么。</p>
      </div>
    </section>

    <section class="filter-bar">
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
          v-model="actionType"
          placeholder="操作类型"
          size="small"
          clearable
          class="filter-item"
          @change="loadData"
        >
          <el-option v-for="a in actions" :key="a" :label="a" :value="a" />
        </el-select>

        <el-input
          v-model="keyword"
          placeholder="关键词搜索"
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
        <el-table-column label="时间" width="165">
          <template #default="{ row }">{{ row.created_at }}</template>
        </el-table-column>

        <el-table-column label="操作类型" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.action }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="目标类型" width="100">
          <template #default="{ row }">{{ row.target_type || '-' }}</template>
        </el-table-column>

        <el-table-column label="目标ID" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_id || '-' }}</template>
        </el-table-column>

        <el-table-column label="详情" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">{{ row.detail || '-' }}</template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[50, 100, 200]"
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
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fetchAuditActions, fetchAuditLogs } from '../api/audit'

const dateRange = ref(null)
const actionType = ref('')
const keyword = ref('')
const actions = ref([])

const tableData = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)

async function loadActions() {
  try {
    const res = await fetchAuditActions()
    actions.value = res.actions || []
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
    if (actionType.value) params.action_type = actionType.value
    if (keyword.value) params.keyword = keyword.value

    const res = await fetchAuditLogs(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error(`加载日志失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

onMounted(() => { loadActions(); loadData() })
</script>

<style scoped>
.audit-page { display: flex; flex-direction: column; gap: 18px; }
.page-banner { display: flex; align-items: flex-start; gap: 16px; padding: 16px 0; }
.page-banner__eyebrow { color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
.page-banner__title { margin: 4px 0 0; font-size: 22px; font-weight: 700; }
.page-banner__desc { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.filter-bar { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { min-width: 140px; }
.table-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.pagination-bar { display: flex; justify-content: center; margin-top: 16px; }
</style>
