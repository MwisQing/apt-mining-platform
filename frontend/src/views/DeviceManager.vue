<template>
  <div class="device-page">
    <section class="page-banner">
      <div>
        <span class="page-banner__eyebrow">设备管理</span>
        <h2 class="page-banner__title">设备列表</h2>
        <p class="page-banner__desc">按设备维度查看标签、事件关联和告警统计。</p>
      </div>
    </section>

    <section class="filter-bar">
      <div class="filter-row">
        <el-input
          v-model="keyword"
          placeholder="搜索设备ID"
          size="small"
          clearable
          class="filter-item"
          @keyup.enter="loadData"
          @clear="loadData"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>

        <el-select
          v-model="tagFilter"
          placeholder="标签筛选"
          size="small"
          clearable
          multiple
          collapse-tags
          class="filter-item"
          @change="loadData"
        >
          <el-option v-for="t in allTags" :key="t.name" :label="t.name" :value="t.name" />
        </el-select>

        <el-button type="primary" size="small" @click="loadData">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </div>
    </section>

    <section class="table-card">
      <el-table :data="tableData" size="small" v-loading="loading" stripe row-key="device_id">
        <el-table-column label="设备ID" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="device-id" @click="copyDeviceId(row.device_id)" title="点击复制">{{ row.device_id }}</span>
          </template>
        </el-table-column>

        <el-table-column label="标签" min-width="180">
          <template #default="{ row }">
            <div class="tag-chips">
              <el-tag v-for="tag in row.device_tags" :key="tag" size="small" class="tag-chip">{{ tag }}</el-tag>
              <span v-if="!row.device_tags.length" class="empty-cell">-</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="告警数" width="80" align="center">
          <template #default="{ row }">{{ row.alert_count }}</template>
        </el-table-column>

        <el-table-column label="事件数" width="80" align="center">
          <template #default="{ row }">{{ row.event_count }}</template>
        </el-table-column>

        <el-table-column label="最后活跃" width="165">
          <template #default="{ row }">{{ row.last_seen || '-' }}</template>
        </el-table-column>

        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openTagEditor(row)">编辑标签</el-button>
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
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </section>

    <el-dialog v-model="tagDialogVisible" :title="'编辑标签: ' + editingDevice.device_id" width="420px">
      <div class="tag-editor">
        <div class="tag-editor__current">
          <div class="tag-editor__label">当前标签：</div>
          <div class="tag-editor__tags">
            <el-tag v-for="tag in currentTags" :key="tag" size="small" closable @close="removeTag(tag)">{{ tag }}</el-tag>
            <span v-if="!currentTags.length" class="empty-cell">无</span>
          </div>
        </div>
        <div class="tag-editor__add">
          <el-select v-model="newTag" placeholder="选择或输入标签" filterable allow-create style="width: 100%">
            <el-option v-for="t in allTags" :key="t.name" :label="t.name" :value="t.name" />
          </el-select>
          <el-button type="primary" size="small" @click="addTag" style="margin-top: 8px">添加</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="tagDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { listDevices, addDeviceTags, removeDeviceTag } from '../api/devices'
import { fetchTags } from '../api/tags'

const keyword = ref('')
const tagFilter = ref([])
const allTags = ref([])

const tableData = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)

const tagDialogVisible = ref(false)
const editingDevice = ref({ device_id: '' })
const currentTags = ref([])
const newTag = ref('')

async function loadAllTags() {
  try {
    allTags.value = await fetchTags()
  } catch { /* ignore */ }
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    if (keyword.value) params.keyword = keyword.value
    if (tagFilter.value.length > 0) params.tags = tagFilter.value.join(',')

    const res = await listDevices(params)
    tableData.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    ElMessage.error(`加载设备列表失败: ${e.message}`)
  } finally {
    loading.value = false
  }
}

function openTagEditor(row) {
  editingDevice.value = { device_id: row.device_id }
  currentTags.value = [...(row.device_tags || [])]
  newTag.value = ''
  tagDialogVisible.value = true
}

async function addTag() {
  if (!newTag.value) return
  try {
    await addDeviceTags(editingDevice.value.device_id, [newTag.value])
    ElMessage.success('标签已添加')
    currentTags.value.push(newTag.value)
    newTag.value = ''
    loadData()
  } catch (e) {
    ElMessage.error(`添加失败: ${e.message}`)
  }
}

async function removeTag(tagName) {
  try {
    await removeDeviceTag(editingDevice.value.device_id, tagName)
    ElMessage.success('标签已移除')
    currentTags.value = currentTags.value.filter(t => t !== tagName)
    loadData()
  } catch (e) {
    ElMessage.error(`移除失败: ${e.message}`)
  }
}

function copyDeviceId(id) {
  navigator.clipboard.writeText(id)
  ElMessage.success('已复制: ' + id)
}

onMounted(() => { loadAllTags(); loadData() })
</script>

<style scoped>
.device-page { display: flex; flex-direction: column; gap: 18px; }
.page-banner { display: flex; align-items: flex-start; gap: 16px; padding: 16px 0; }
.page-banner__eyebrow { color: var(--accent); font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
.page-banner__title { margin: 4px 0 0; font-size: 22px; font-weight: 700; }
.page-banner__desc { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.filter-bar { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.filter-item { min-width: 140px; }
.table-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; padding: 16px; }
.pagination-bar { display: flex; justify-content: center; margin-top: 16px; }
.empty-cell { color: var(--text-muted); }
.device-id { cursor: pointer; color: var(--accent); }
.device-id:hover { text-decoration: underline; }
.tag-chips { display: flex; gap: 4px; flex-wrap: wrap; }
.tag-chip { margin: 0; }
.tag-editor { display: flex; flex-direction: column; gap: 16px; }
.tag-editor__label { font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.tag-editor__tags { display: flex; gap: 4px; flex-wrap: wrap; min-height: 28px; }
.tag-editor__add { display: flex; flex-direction: column; }
</style>
