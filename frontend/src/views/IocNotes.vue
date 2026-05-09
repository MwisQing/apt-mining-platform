<template>
  <div class="ioc-notes-page">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">IOC 备注</span>
        <h2 class="page-banner__title">IOC 备注管理</h2>
        <p class="page-banner__desc">沉淀已确认目标的注释，帮助后续批次快速继承历史判断。</p>
      </div>
      <div class="page-banner__stats">
        <div class="stat-pill">
          <span>备注总数</span>
          <strong>{{ total }}</strong>
        </div>
        <div class="stat-pill">
          <span>已选条目</span>
          <strong>{{ selectedIds.size }}</strong>
        </div>
      </div>
    </section>

    <section class="toolbar-card">
      <div class="page-header">
        <div>
          <div class="section-title">检索与管理</div>
          <div class="section-hint">支持关键词检索、单条编辑和批量删除。</div>
        </div>
        <div class="header-actions">
          <el-button type="danger" size="small" @click="handleBatchDelete" :disabled="selectedIds.size === 0">
            <el-icon><Delete /></el-icon>
            批量删除 ({{ selectedIds.size }})
          </el-button>
          <el-button type="primary" size="small" @click="showAddDialog">
            <el-icon><Plus /></el-icon>
            添加备注
          </el-button>
          <el-button size="small" @click="loadData" :loading="loading">
            <el-icon><RefreshRight /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="filter-bar">
        <el-input
          v-model="keyword"
          placeholder="搜索目标或备注..."
          size="small"
          clearable
          class="keyword-input"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" size="small" @click="handleSearch">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </div>
    </section>

    <section class="table-card">
      <el-table
        ref="tableRef"
        :data="tableData"
        size="small"
        v-loading="loading"
        stripe
        row-key="id"
        class="notes-table"
        :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column prop="target" label="目标" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="target-cell">{{ row.target }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="port" label="端口" width="80" align="center">
          <template #default="{ row }">
            {{ row.port || '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="note-cell">{{ row.note || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="traced_at" label="添加时间" width="170" />
        <el-table-column label="操作" width="140" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="showEditDialog(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
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
          @size-change="paginate"
          @current-change="paginate"
        />
      </div>
    </section>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑备注' : '添加备注'" width="450px">
      <el-form :model="form" label-width="60px">
        <el-form-item label="目标" required>
          <el-input v-model="form.target" placeholder="IP 或域名" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input v-model="form.port" placeholder="可选" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="4" placeholder="输入备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Delete, Plus, RefreshRight, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createTraced, deleteTraced, fetchTracedList, updateTraced } from '../api/traced'

const allData = ref([])
const tableData = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)
const keyword = ref('')
const selectedIds = ref(new Set())

function handleSelectionChange(rows) {
  selectedIds.value = new Set(rows.map((r) => r.id))
}

function paginate() {
  const start = (currentPage.value - 1) * pageSize.value
  tableData.value = allData.value.slice(start, start + pageSize.value)
  total.value = allData.value.length
}

async function loadData() {
  loading.value = true
  try {
    const params = {}
    if (keyword.value) params.keyword = keyword.value.trim()
    const res = await fetchTracedList(params)
    allData.value = Array.isArray(res) ? res : (res.items || [])
    currentPage.value = 1
    paginate()
  } catch (e) {
    ElMessage.error(`加载 IOC 备注失败: ${e.message}`)
    allData.value = []
    paginate()
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  keyword.value = keyword.value.trim()
  currentPage.value = 1
  loadData()
}

const dialogVisible = ref(false)
const editingId = ref(null)
const saving = ref(false)
const form = ref({ target: '', port: '', note: '' })

function showAddDialog() {
  editingId.value = null
  form.value = { target: '', port: '', note: '' }
  dialogVisible.value = true
}

function showEditDialog(row) {
  editingId.value = row.id
  form.value = { target: row.target, port: row.port || '', note: row.note || '' }
  dialogVisible.value = true
}

async function confirmSave() {
  if (!form.value.target) {
    ElMessage.warning('目标不能为空')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateTraced(editingId.value, form.value)
      ElMessage.success('更新成功')
    } else {
      await createTraced(form.value)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    loadData()
  } catch (e) {
    ElMessage.error(`保存失败: ${e.message}`)
  } finally {
    saving.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除 ${row.target}:${row.port || ''} 的备注吗？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteTraced(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) {
    ElMessage.error(`删除失败: ${e.message}`)
  }
}

async function handleBatchDelete() {
  if (selectedIds.value.size === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.size} 条备注吗？`, '批量删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }

  const ids = [...selectedIds.value]
  let deleted = 0
  for (const id of ids) {
    try {
      await deleteTraced(id)
      deleted += 1
    } catch (e) {
      /* continue */
    }
  }
  if (deleted > 0) {
    ElMessage.success(`成功删除 ${deleted} 条备注`)
  }
  selectedIds.value = new Set()
  loadData()
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.ioc-notes-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.page-banner,
.toolbar-card,
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

.toolbar-card,
.table-card {
  padding: 16px 18px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.section-title {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 700;
}

.section-hint {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.filter-bar {
  margin-top: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.keyword-input {
  width: 320px;
}

.notes-table {
  flex: 1;
}

.notes-table :deep(.el-table__body-wrapper) {
  background-color: var(--table-row-bg);
}

.notes-table :deep(.el-table__body tr) {
  background-color: var(--table-row-bg);
}

.notes-table :deep(.el-table__body tr:hover > td) {
  background-color: var(--table-row-hover) !important;
}

.notes-table :deep(.el-table__body tr.el-table__row--striped td) {
  background-color: var(--table-row-stripe);
}

.target-cell {
  font-family: "Consolas", monospace;
  font-size: 12px;
  color: var(--text-primary);
}

.note-cell {
  color: var(--text-secondary);
}

.pagination-bar {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  padding: 8px 0;
}

@media (max-width: 960px) {
  .page-banner,
  .page-banner__stats,
  .page-header,
  .filter-bar,
  .header-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .keyword-input {
    width: 100%;
  }
}
</style>
