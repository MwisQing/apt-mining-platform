<template>
  <div class="workbench">
    <section class="filter-bar">
      <div class="filter-bar__intro">
        <div>
          <div class="filter-bar__title">筛选条件</div>
          <div class="filter-bar__hint">按日期、目标类型和关键字缩小候选范围。</div>
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
          format="YYYY年MM月DD日"
          value-format="YYYY-MM-DD"
          size="small"
          class="filter-item date-picker"
          @change="handleSearch"
        />

        <el-button-group class="filter-item">
          <el-button :type="targetKind === 'all' ? 'primary' : ''" size="small" @click="setTargetKind('all')">
            全部
          </el-button>
          <el-button :type="targetKind === 'ip' ? 'primary' : ''" size="small" @click="setTargetKind('ip')">
            仅 IP
          </el-button>
          <el-button :type="targetKind === 'domain' ? 'primary' : ''" size="small" @click="setTargetKind('domain')">
            仅域名
          </el-button>
        </el-button-group>

        <div class="filter-item switch-group">
          <span class="switch-label">隐藏已追踪</span>
          <el-switch v-model="hideTraced" size="small" @change="handleSearch" />
        </div>

        <el-select
          v-model="excludeTags"
          multiple
          filterable
          placeholder="排除标签"
          size="small"
          clearable
          class="filter-item exclude-select"
          @change="handleSearch"
        >
          <el-option
            v-for="tag in tagOptions"
            :key="tag.id"
            :label="tag.name"
            :value="tag.id"
          />
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

        <el-button type="primary" size="small" @click="handleSearch" class="filter-item">
          <el-icon><Search /></el-icon>
          查询
        </el-button>

        <el-popover placement="bottom-end" :width="220" trigger="click">
          <template #reference>
            <el-button size="small" class="filter-item">
              <el-icon><Operation /></el-icon>
              列设置
            </el-button>
          </template>
          <div class="column-selector">
            <el-checkbox
              v-for="col in allColumns()"
              :key="col.key"
              :model-value="col.visible"
              size="small"
              @change="toggleColumn(col.key)"
            >
              {{ col.label }}
            </el-checkbox>
            <div class="column-selector__actions">
              <el-button
                size="small"
                @click="handleResetColumnSettings"
              >
                恢复默认
              </el-button>
              <el-button
                type="primary"
                size="small"
                :disabled="!hasPendingColumnChanges"
                @click="handleSaveColumnSettings"
              >
                保存当前设置
              </el-button>
            </div>
          </div>
        </el-popover>
      </div>
    </section>

    <section class="table-card">
      <div class="table-card__header">
        <div>
          <div class="table-card__title">候选清单</div>
          <div class="table-card__hint">支持自定义列宽、列显隐和快捷标签编辑。</div>
        </div>
        <div class="table-card__meta">
          <span class="table-chip">第 {{ currentPage }} 页</span>
          <span class="table-chip">{{ pageSize }} / 页</span>
        </div>
      </div>

      <el-table
        ref="tableRef"
        :data="displayData"
        size="small"
        v-loading="loading"
        stripe
        row-key="id"
        :row-class-name="rowClassName"
        class="candidates-table"
        :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
      >
        <el-table-column v-if="colVisible('priority')" :width="colWidth('priority')" :resizable="false" fixed>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('priority') }}</span>
              <el-popover trigger="click" :width="180" placement="bottom-end">
                <template #reference>
                  <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('priority') }">
                    <Filter />
                  </el-icon>
                </template>
                <div class="column-filter">
                  <el-checkbox-group v-model="columnFilters.priority" class="column-filter-group">
                    <el-checkbox v-for="val in _extractValues('priority')" :key="val" :label="val" :value="val">
                      {{ val }}
                    </el-checkbox>
                  </el-checkbox-group>
                  <div class="column-filter__actions">
                    <el-button size="small" text @click="columnFilters.priority = _extractValues('priority')">全选</el-button>
                    <el-button size="small" text @click="clearFilter('priority')">清空</el-button>
                  </div>
                </div>
              </el-popover>
              <span class="resize-handle" @mousedown.stop="onResizeStart('priority', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <el-tag :color="priorityColor(row.candidate_priority?.id)" :style="{ color: '#fff', border: 'none' }" size="small">
              {{ row.candidate_priority?.label || '-' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('score')"
          :width="colWidth('score')"
          prop="candidate_score"
          align="center"
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('score') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="score" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('score', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span class="score-cell">{{ row.candidate_score ?? '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('device_id')"
          :width="colWidth('device_id')"
          prop="device_id"
          show-overflow-tooltip
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('device_id') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="device_id" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('device_id', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span class="device-id">{{ row.device_id }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="colVisible('device_tags')" :width="colWidth('device_tags')">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('device_tags') }}</span>
              <el-popover trigger="click" :width="220" placement="bottom-end">
                <template #reference>
                  <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('device_tags') }">
                    <Filter />
                  </el-icon>
                </template>
                <div class="column-filter">
                  <el-checkbox-group v-model="columnFilters.device_tags" class="column-filter-group">
                    <el-checkbox v-for="val in _extractValues('device_tags')" :key="val" :label="val" :value="val">
                      {{ val }}
                    </el-checkbox>
                  </el-checkbox-group>
                  <div class="column-filter__actions">
                    <el-button size="small" text @click="columnFilters.device_tags = _extractValues('device_tags')">全选</el-button>
                    <el-button size="small" text @click="clearFilter('device_tags')">清空</el-button>
                  </div>
                </div>
              </el-popover>
              <span class="resize-handle" @mousedown.stop="onResizeStart('device_tags', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <el-popover placement="bottom" :width="300" trigger="click" @show="openTagEditor(row)">
              <template #reference>
                <div class="device-tags-cell">
                  <template v-if="row.device_tags?.length">
                    <el-tag
                      v-for="tag in row.device_tags"
                      :key="tag.id"
                      :color="tag.color"
                      :style="{ color: '#fff', border: 'none', marginRight: '4px' }"
                      size="small"
                    >
                      {{ tag.name }}
                    </el-tag>
                  </template>
                  <span v-else class="empty-cell tag-placeholder">+</span>
                </div>
              </template>

              <div class="tag-editor">
                <div class="tag-editor-title">设备 {{ row.device_id }}</div>
                <div class="tag-editor-current">
                  <span class="tag-editor-label">当前标签</span>
                  <template v-if="editingTags.length">
                    <el-tag
                      v-for="tag in editingTags"
                      :key="tag.id"
                      :color="tag.color"
                      :style="{ color: '#fff', border: 'none', marginRight: '4px', marginBottom: '4px' }"
                      size="small"
                      closable
                      @close="handleRemoveTag(row.device_id, tag.id)"
                    >
                      {{ tag.name }}
                    </el-tag>
                  </template>
                  <span v-else class="empty-cell">暂无</span>
                </div>
                <div class="tag-editor-add">
                  <el-select
                    ref="tagSelectRef"
                    v-model="newTagName"
                    filterable
                    allow-create
                    default-first-option
                    placeholder="输入或选择标签名"
                    size="small"
                    class="tag-editor-select"
                    @keyup.enter="handleAddTag(row.device_id)"
                  >
                    <el-option v-for="name in allTagNames" :key="name" :label="name" :value="name" />
                  </el-select>
                  <el-color-picker v-model="newTagColor" size="small" />
                  <el-button size="small" type="primary" @click="handleAddTag(row.device_id)">添加</el-button>
                </div>
              </div>
            </el-popover>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('device_target_count')"
          :width="colWidth('device_target_count')"
          prop="heat.device_target_count"
          align="center"
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('device_target_count') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="device_target_count" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('device_target_count', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span class="count-cell">{{ row.heat?.device_target_count || 0 }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('source_ip')"
          :width="colWidth('source_ip')"
          prop="source_ip"
          show-overflow-tooltip
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('source_ip') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="source_ip" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('source_ip', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <el-tooltip
              :content="sourceIpPreview(row)"
              placement="top"
              :disabled="!hasMultipleSourceIps(row)"
            >
              <span class="source-ip">{{ row.source_ips || row.source_ip || '-' }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('source_ip_count')"
          :width="colWidth('source_ip_count')"
          prop="source_ip_count"
          align="center"
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('source_ip_count') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="source_ip_count" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('source_ip_count', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span class="count-cell">{{ row.source_ip_count ?? (row.source_ip ? 1 : 0) }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('target')"
          :width="colWidth('target')"
          prop="target"
          show-overflow-tooltip
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('target') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="target" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('target', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span class="target-cell">{{ row.target }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('port')"
          :width="colWidth('port')"
          prop="port"
          align="center"
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('port') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="port" @sort="handleSortClick" />
              <el-popover trigger="click" :width="220" placement="bottom-end">
                <template #reference>
                  <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('port') }">
                    <Filter />
                  </el-icon>
                </template>
                <div class="column-filter">
                  <el-checkbox-group v-model="columnFilters.port" class="column-filter-group">
                    <el-checkbox v-for="val in _extractValues('port')" :key="val" :label="val" :value="val">
                      {{ val || '(空)' }}
                    </el-checkbox>
                  </el-checkbox-group>
                  <div class="column-filter__actions">
                    <el-button size="small" text @click="columnFilters.port = _extractValues('port')">全选</el-button>
                    <el-button size="small" text @click="clearFilter('port')">清空</el-button>
                  </div>
                </div>
              </el-popover>
              <span class="resize-handle" @mousedown.stop="onResizeStart('port', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            {{ row.port || '-' }}
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('device_alert_count')"
          :width="colWidth('device_alert_count')"
          prop="device_alert_count"
          align="center"
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('device_alert_count') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="device_alert_count" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('device_alert_count', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span class="count-cell">{{ row.heat?.device_alert_count || 0 }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="colVisible('ioc_note')" :width="colWidth('ioc_note')" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('ioc_note') }}</span>
              <el-popover trigger="click" :width="240" placement="bottom-end">
                <template #reference>
                  <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('ioc_note') }">
                    <Filter />
                  </el-icon>
                </template>
                <div class="column-filter">
                  <el-input
                    v-model="columnFilters.ioc_note"
                    placeholder="输入关键词过滤"
                    size="small"
                    clearable
                  >
                    <template #prefix>
                      <el-icon><Search /></el-icon>
                    </template>
                  </el-input>
                </div>
              </el-popover>
              <span class="resize-handle" @mousedown.stop="onResizeStart('ioc_note', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="row.ioc_note" class="ioc-note-cell">{{ row.ioc_note }}</span>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>

        <el-table-column v-if="colVisible('event')" :width="colWidth('event')" show-overflow-tooltip>
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('event') }}</span>
              <span class="resize-handle" @mousedown.stop="onResizeStart('event', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <el-tag
              v-if="row.event"
              :color="row.event.color || '#409EFF'"
              size="small"
              :style="{ color: '#fff', border: 'none' }"
            >
              {{ row.event.event_name }}
            </el-tag>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('threat_type')"
          :width="colWidth('threat_type')"
          prop="threat_type"
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('threat_type') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="threat_type" @sort="handleSortClick" />
              <el-popover trigger="click" :width="220" placement="bottom-end">
                <template #reference>
                  <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('threat_type') }">
                    <Filter />
                  </el-icon>
                </template>
                <div class="column-filter">
                  <el-checkbox-group v-model="columnFilters.threat_type" class="column-filter-group">
                    <el-checkbox v-for="val in _extractValues('threat_type')" :key="val" :label="val" :value="val">
                      {{ val }}
                    </el-checkbox>
                  </el-checkbox-group>
                  <div class="column-filter__actions">
                    <el-button size="small" text @click="columnFilters.threat_type = _extractValues('threat_type')">全选</el-button>
                    <el-button size="small" text @click="clearFilter('threat_type')">清空</el-button>
                  </div>
                </div>
              </el-popover>
              <span class="resize-handle" @mousedown.stop="onResizeStart('threat_type', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <el-tag :type="threatTypeTag(row.threat_type)" size="small">{{ row.threat_type || '-' }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('std_apt_org')"
          :width="colWidth('std_apt_org')"
          prop="std_apt_org"
          show-overflow-tooltip
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('std_apt_org') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="std_apt_org" @sort="handleSortClick" />
              <el-popover trigger="click" :width="220" placement="bottom-end">
                <template #reference>
                  <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('std_apt_org') }">
                    <Filter />
                  </el-icon>
                </template>
                <div class="column-filter">
                  <el-checkbox-group v-model="columnFilters.std_apt_org" class="column-filter-group">
                    <el-checkbox v-for="val in _extractValues('std_apt_org')" :key="val" :label="val" :value="val">
                      {{ val }}
                    </el-checkbox>
                  </el-checkbox-group>
                  <div class="column-filter__actions">
                    <el-button size="small" text @click="columnFilters.std_apt_org = _extractValues('std_apt_org')">全选</el-button>
                    <el-button size="small" text @click="clearFilter('std_apt_org')">清空</el-button>
                  </div>
                </div>
              </el-popover>
              <span class="resize-handle" @mousedown.stop="onResizeStart('std_apt_org', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            {{ row.std_apt_org || '-' }}
          </template>
        </el-table-column>

        <el-table-column v-if="colVisible('analysis_status')" :width="colWidth('analysis_status')" align="center">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('analysis_status') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="analysis_status" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('analysis_status', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span class="empty-cell">{{ row.analysis_status || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column
          v-if="colVisible('heat')"
          :width="colWidth('heat')"
          prop="heat.target_alert_count"
          align="center"
        >
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('heat') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="heat" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('heat', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <span v-if="row.heat" class="heat-cell">
              {{ row.heat.target_alert_count }} 条 / {{ row.heat.target_device_count }} 台
            </span>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>

        <el-table-column v-if="colVisible('is_focused')" :width="colWidth('is_focused')" align="center">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('is_focused') }}</span>
              <SortButton :active="sortField" :order="sortOrder" column-key="is_focused" @sort="handleSortClick" />
              <span class="resize-handle" @mousedown.stop="onResizeStart('is_focused', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <el-icon v-if="row.is_focused" color="#F56C6C" :size="16"><StarFilled /></el-icon>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>

        <el-table-column v-if="colVisible('candidate_reasons')" :width="colWidth('candidate_reasons')">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('candidate_reasons') }}</span>
              <span class="resize-handle" @mousedown.stop="onResizeStart('candidate_reasons', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <template v-if="row.candidate_reasons?.length">
              <el-tag
                v-for="(reason, idx) in row.candidate_reasons"
                :key="idx"
                size="small"
                class="reason-tag"
                effect="dark"
              >
                {{ reason }}
              </el-tag>
            </template>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>

        <el-table-column v-if="colVisible('badges')" :width="colWidth('badges')">
          <template #header>
            <div class="resizable-header">
              <span class="col-label-text">{{ colLabel('badges') }}</span>
              <el-popover trigger="click" :width="220" placement="bottom-end">
                <template #reference>
                  <el-icon class="header-filter-icon" :class="{ 'is-active': hasFilter('badges') }">
                    <Filter />
                  </el-icon>
                </template>
                <div class="column-filter">
                  <el-checkbox-group v-model="columnFilters.badges" class="column-filter-group">
                    <el-checkbox v-for="val in _extractValues('badges')" :key="val" :label="val" :value="val">
                      {{ val }}
                    </el-checkbox>
                  </el-checkbox-group>
                  <div class="column-filter__actions">
                    <el-button size="small" text @click="columnFilters.badges = _extractValues('badges')">全选</el-button>
                    <el-button size="small" text @click="clearFilter('badges')">清空</el-button>
                  </div>
                </div>
              </el-popover>
              <span class="resize-handle" @mousedown.stop="onResizeStart('badges', $event)"></span>
            </div>
          </template>
          <template #default="{ row }">
            <template v-if="row.badges?.length">
              <el-tag
                v-for="badge in row.badges"
                :key="badge.name"
                :color="badge.color"
                :style="{ color: '#fff', border: 'none', marginRight: '4px' }"
                size="small"
              >
                {{ badge.label }}
              </el-tag>
            </template>
            <span v-else class="empty-cell">-</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="displayTotal"
          :page-sizes="[50, 100, 200]"
          layout="total, sizes, prev, pager, next"
          background
          @size-change="handlePageSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { CaretTop, CaretBottom, Filter, Operation, RefreshRight, Search, StarFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { fetchCandidates } from '../api/candidates'
import { fetchConfig } from '../api/config'
import { useColumnConfig } from '../composables/useColumnConfig'
import { addDeviceTag, fetchTags, removeDeviceTag } from '../api/tags'

const { columns, allColumns, toggleColumn, persistColumns, resetColumns, hasPendingChanges, onResizeStart } = useColumnConfig()

function colVisible(key) {
  return columns.value.find((c) => c.key === key)?.visible !== false
}

function colWidth(key) {
  return columns.value.find((c) => c.key === key)?.width || 100
}

function colLabel(key) {
  return columns.value.find((c) => c.key === key)?.label || key
}

const hasPendingColumnChanges = computed(() => hasPendingChanges.value)

function handleSaveColumnSettings() {
  persistColumns()
  ElMessage.success('列设置已保存')
}

function handleResetColumnSettings() {
  resetColumns()
  ElMessage.success('已恢复为默认列设置')
}

function hasMultipleSourceIps(row) {
  return typeof row?.source_ips === 'string' && row.source_ips.includes('|')
}

function sourceIpPreview(row) {
  return row?.source_ips || row?.source_ip || '-'
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
  allDataLoaded = false
  loadData()
}

const SortButton = {
  props: ['active', 'order', 'columnKey'],
  emits: ['sort'],
  render() {
    const { active, order, columnKey } = this
    const isActive = active === columnKey
    return h('span', {
      class: ['sort-button', { 'is-active': isActive }],
      title: '排序',
      onClick: (e) => { e.stopPropagation(); this.$emit('sort', columnKey) },
    }, [
      h(CaretTop, { class: { active: isActive && order === 'asc' } }),
      h(CaretBottom, { class: { active: isActive && order === 'desc' } }),
    ])
  },
}

const editingDeviceId = ref('')
const editingTags = ref([])
const newTagName = ref('')
const newTagColor = ref('#409EFF')
const allTagNames = ref([])
const tagSelectRef = ref(null)

async function openTagEditor(row) {
  editingDeviceId.value = row.device_id
  editingTags.value = row.device_tags ? [...row.device_tags] : []
  newTagName.value = ''
  newTagColor.value = '#409EFF'
  try {
    const tags = await fetchTags()
    allTagNames.value = (Array.isArray(tags) ? tags : []).map((t) => t.name).filter(Boolean)
  } catch (e) {
    /* silent */
  }
}

function getEffectiveTagName() {
  if (newTagName.value) return newTagName.value.trim()
  const sel = tagSelectRef.value
  if (sel && sel.query) return sel.query.trim()
  return ''
}

async function handleAddTag(deviceId) {
  const name = getEffectiveTagName()
  if (!name) return
  try {
    await addDeviceTag(deviceId, {
      tag_name: name,
      color: newTagColor.value,
    })
    newTagName.value = ''
    newTagColor.value = '#409EFF'
    if (tagSelectRef.value) tagSelectRef.value.query = ''
    try {
      const tags = await fetchTags()
      allTagNames.value = (Array.isArray(tags) ? tags : []).map((t) => t.name).filter(Boolean)
    } catch (e) {
      /* silent */
    }
    loadData()
    ElMessage.success('标签已添加')
  } catch (e) {
    ElMessage.error(`添加标签失败: ${e.message}`)
  }
}

async function handleRemoveTag(deviceId, tagId) {
  try {
    await removeDeviceTag(deviceId, tagId)
    editingTags.value = editingTags.value.filter((t) => t.id !== tagId)
    loadData()
    ElMessage.success('标签已移除')
  } catch (e) {
    ElMessage.error(`移除标签失败: ${e.message}`)
  }
}

function getDefaultDateRange() {
  const today = new Date()
  return [formatDate(today), formatDate(today)]
}

function formatDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const dateRange = ref(getDefaultDateRange())
const targetKind = ref('all')
const hideTraced = ref(true)
const excludeTags = ref([])
const tagOptions = ref([])
const keyword = ref('')
const sortField = ref('')
const sortOrder = ref('')

const tableData = shallowRef([])
const allTableData = shallowRef([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(0)
let requestSeq = 0
let allDataLoaded = false

async function loadConfig() {
  try {
    const cfg = await fetchConfig()
    if (cfg.default_hide_traced !== undefined) {
      hideTraced.value = cfg.default_hide_traced
    }
  } catch (e) {
    /* ignore */
  }
}

async function loadTagOptions() {
  try {
    const tags = await fetchTags()
    tagOptions.value = (Array.isArray(tags) ? tags : []).map((t) => ({ id: String(t.id), name: t.name })).filter((t) => t.name)
  } catch (e) {
    /* ignore */
  }
}

async function loadData(forceAllData = false) {
  const needAllData = forceAllData || FILTERABLE_COLUMNS.some(k => hasFilter(k))
  const requestId = ++requestSeq
  loading.value = true
  try {
    const params = {
      hide_traced: hideTraced.value,
    }

    if (needAllData) {
      params.page = 1
      params.page_size = 99999
    } else {
      params.page = currentPage.value
      params.page_size = pageSize.value
    }

    if (dateRange.value && dateRange.value.length === 2) {
      params.date_start = dateRange.value[0]
      params.date_end = dateRange.value[1]
    }

    if (targetKind.value !== 'all') params.target_kind = targetKind.value
    if (keyword.value) params.keyword = keyword.value
    if (excludeTags.value.length > 0) params.exclude_device_tags = excludeTags.value.join(',')
    if (sortField.value) {
      params.sort_by = sortField.value
      params.sort_order = sortOrder.value
    }

    const res = await fetchCandidates(params)
    if (requestId !== requestSeq) return
    const items = res.items || []
    total.value = res.total || 0
    if (res.filter_options) {
      filterOptions.value = res.filter_options
    }

    if (needAllData) {
      allTableData.value = items
      allDataLoaded = true
      tableData.value = items
    } else {
      allDataLoaded = false
      allTableData.value = []
      tableData.value = items
    }
  } catch (e) {
    if (requestId !== requestSeq) return
    ElMessage.error(`加载候选数据失败: ${e.message}`)
    tableData.value = []
    allTableData.value = []
    allDataLoaded = false
    total.value = 0
  } finally {
    if (requestId === requestSeq) loading.value = false
  }
}

function handleSearch() {
  keyword.value = keyword.value.trim()
  currentPage.value = 1
  allDataLoaded = false
  loadData()
}

function setTargetKind(kind) {
  targetKind.value = kind
  handleSearch()
}

function handlePageChange() {
  if (!allDataLoaded) loadData()
}

function handlePageSizeChange() {
  currentPage.value = 1
  if (!allDataLoaded) loadData()
}

// --- Column header filtering ---

const columnFilters = reactive({
  device_tags: [],
  threat_type: [],
  std_apt_org: [],
  priority: [],
  port: [],
  badges: [],
  ioc_note: '',
})

const FILTERABLE_COLUMNS = ['device_tags', 'threat_type', 'std_apt_org', 'priority', 'port', 'badges', 'ioc_note']

const filterOptions = ref({})

function hasFilter(key) {
  if (key === 'ioc_note') return !!columnFilters.ioc_note
  return Array.isArray(columnFilters[key]) && columnFilters[key].length > 0
}

function clearFilter(key) {
  if (key === 'ioc_note') {
    columnFilters.ioc_note = ''
  } else {
    columnFilters[key] = []
  }
}

function _extractValues(key) {
  if (key === 'priority') return ['高优先', '中优先', '观察']
  return (filterOptions.value[key] || []).slice()
}

function _rowMatchesFilter(row, key) {
  const filter = columnFilters[key]
  if (!filter || (Array.isArray(filter) && filter.length === 0)) return true
  if (key === 'ioc_note') {
    if (!filter) return true
    const note = row.ioc_note || ''
    return note.toLowerCase().includes(filter.toLowerCase())
  }
  if (key === 'device_tags') {
    const tagNames = (row.device_tags || []).map(t => t.name)
    return filter.some(f => tagNames.includes(f))
  }
  if (key === 'priority') {
    const label = row.candidate_priority?.label || '观察'
    return filter.includes(label)
  }
  if (key === 'badges') {
    const badgeLabels = (row.badges || []).map(b => b.label)
    return filter.some(f => badgeLabels.includes(f))
  }
  const rowVal = row[key] != null ? String(row[key]) : ''
  return filter.includes(rowVal)
}

// 全量过滤后的数据（表头筛选作用于全部数据，而非仅当前页）
const allFilteredData = computed(() => {
  const source = allDataLoaded ? allTableData.value : tableData.value
  const activeFilters = FILTERABLE_COLUMNS.filter(k => hasFilter(k))
  if (activeFilters.length === 0) return source
  return source.filter(row =>
    activeFilters.every(key => _rowMatchesFilter(row, key))
  )
})

// 过滤后的总数
const totalFiltered = computed(() => allFilteredData.value.length)

// 分页展示数据
const displayData = computed(() => {
  if (allDataLoaded) {
    const start = (currentPage.value - 1) * pageSize.value
    return allFilteredData.value.slice(start, start + pageSize.value)
  }
  return allFilteredData.value
})

const displayTotal = computed(() => {
  if (FILTERABLE_COLUMNS.some(k => hasFilter(k))) return totalFiltered.value
  return total.value
})

// 当表头筛选条件变化时，自动回到第 1 页，并在需要时加载全量数据
watch(
  () => Object.values(columnFilters),
  () => {
    const anyFilterActive = FILTERABLE_COLUMNS.some(k => hasFilter(k))
    currentPage.value = 1
    if (anyFilterActive && !allDataLoaded) {
      loadData(true)
    } else if (!anyFilterActive && allDataLoaded) {
      loadData()
    }
  },
  { deep: true },
)

function rowClassName({ row }) {
  const id = row.candidate_priority?.id
  if (id === 'p1') return 'row-high-priority'
  if (id === 'p2') return 'row-medium-priority'
  return ''
}

function priorityColor(id) {
  switch (id) {
    case 'p1':
      return '#F56C6C'
    case 'p2':
      return '#E6A23C'
    default:
      return '#909399'
  }
}

function threatTypeTag(type) {
  if (!type) return 'info'
  const lower = type.toLowerCase()
  if (lower.includes('apt')) return 'danger'
  if (lower.includes('远控') || lower.includes('remote')) return 'warning'
  return 'info'
}

onMounted(async () => {
  await loadConfig()
  await loadTagOptions()
  loadData()
})
</script>

<style scoped>
.workbench {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.filter-bar {
  padding: 16px 18px;
  background: var(--panel-strong);
  border-radius: 10px;
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-card);
}

.filter-bar__intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.filter-bar__title {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 700;
}

.filter-bar__hint {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
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

.keyword-input {
  width: 180px;
}

.exclude-select {
  width: 200px;
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

.column-selector {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 300px;
  overflow-y: auto;
}

.column-selector__actions {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}

.table-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 16px 18px 12px;
  border-radius: 10px;
  background: var(--panel-strong);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-card);
}

.table-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.table-card__title {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 700;
}

.table-card__hint {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.table-card__meta {
  display: flex;
  gap: 8px;
}

.table-chip {
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
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

.header-filter-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  cursor: pointer;
  color: var(--text-muted);
  transition: color 0.15s;
  position: relative;
  margin-left: 4px;
  margin-right: 6px;
}
.header-filter-icon:hover { color: var(--accent); }
.header-filter-icon.is-active { color: var(--accent); }
.header-filter-icon.is-active::after {
  content: '';
  position: absolute;
  top: -2px; right: -2px;
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--accent);
}

.column-filter {
  display: flex;
  flex-direction: column;
  max-height: 280px;
}
.column-filter-group {
  overflow-y: auto;
  max-height: 240px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.column-filter__actions {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color);
}

.resize-handle {
  position: absolute;
  right: -1px;
  top: 4px;
  bottom: 4px;
  width: 8px;
  cursor: col-resize;
  z-index: 2;
  border-right: 2px solid var(--border-color);
  border-radius: 1px;
  transition: border-color 0.15s;
}

.resize-handle:hover {
  border-color: var(--accent);
  background: var(--accent);
  opacity: 0.4;
}

.sort-button {
  flex-shrink: 0;
  width: 24px;
  height: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.15s;
  gap: 0;
  line-height: 1;
  opacity: 0.5;
  color: var(--text-muted);
}
.sort-button:hover {
  background: var(--bg-tertiary);
  opacity: 1;
  color: var(--text-primary);
}
.sort-button.is-active {
  opacity: 1;
  color: var(--accent);
}
.sort-button :deep(.active) {
  color: var(--accent);
}
.sort-button :deep(svg) {
  width: 12px;
  height: 12px;
}

.candidates-table {
  flex: 1;
}

.candidates-table :deep(.el-table__body-wrapper) {
  background-color: var(--table-row-bg);
}

.candidates-table :deep(.el-table__body tr) {
  background-color: var(--table-row-bg);
}

.candidates-table :deep(.el-table__body tr:hover > td) {
  background-color: var(--table-row-hover) !important;
}

.candidates-table :deep(.el-table__body tr.el-table__row--striped td) {
  background-color: var(--table-row-stripe);
}

.candidates-table :deep(.row-high-priority),
.candidates-table :deep(.row-medium-priority) {
  position: relative;
}

.candidates-table :deep(.row-high-priority)::before,
.candidates-table :deep(.row-medium-priority)::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  z-index: 1;
}

.candidates-table :deep(.row-high-priority)::before {
  background: #f87171;
}

.candidates-table :deep(.row-medium-priority)::before {
  background: #f5a623;
}

.device-id,
.source-ip {
  font-family: "Consolas", monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.target-cell,
.score-cell,
.count-cell {
  color: var(--text-primary);
}

.score-cell,
.count-cell {
  font-weight: 700;
}

.empty-cell {
  color: var(--text-muted);
}

.ioc-note-cell,
.heat-cell {
  font-size: 12px;
  color: var(--text-secondary);
}

.reason-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.pagination-bar {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  padding: 8px 0;
}

.device-tags-cell {
  cursor: pointer;
  min-height: 20px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  padding: 2px 0;
}

.device-tags-cell:hover {
  opacity: 0.88;
}

.tag-placeholder {
  font-size: 16px;
}

.tag-editor-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-color);
}

.tag-editor-current {
  margin-bottom: 12px;
}

.tag-editor-label {
  font-size: 12px;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 6px;
}

.tag-editor-add {
  display: flex;
  gap: 6px;
  align-items: center;
}

.tag-editor-select {
  flex: 1;
}

@media (max-width: 720px) {
  .filter-bar__intro,
  .table-card__header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
