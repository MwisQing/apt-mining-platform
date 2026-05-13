<template>
  <div class="settings-page">
    <h2 class="page-title">导入与设置</h2>

    <el-tabs v-model="activeTab" class="settings-tabs">
      <!-- Tab 1: 数据导入 -->
      <el-tab-pane label="数据导入" name="import">
        <div class="tab-content">
          <!-- 上传区 -->
          <el-card class="section-card">
            <template #header>
              <span class="card-title">上传告警Excel</span>
            </template>
            <el-upload
              drag
              multiple
              :accept="'.xlsx,.xls'"
              :before-upload="beforeUploadExcel"
              :http-request="handleUploadExcel"
              :show-file-list="false"
            >
              <div class="upload-area">
                <el-icon class="upload-icon"><UploadFilled /></el-icon>
                <p>拖拽文件到此处，或 <em>点击上传</em></p>
                <p class="upload-hint">支持 .xlsx / .xls 格式，可同时选择多个文件</p>
              </div>
            </el-upload>

            <!-- 上传进度 -->
            <div v-if="uploadProgress > 0" class="upload-progress">
              <div class="upload-progress__label">
                <span>上传中：{{ uploadingFileName }}</span>
                <span class="upload-progress__pct">{{ uploadProgress }}%</span>
              </div>
              <el-progress :percentage="uploadProgress" :stroke-width="8" :show-text="false" />
            </div>

            <!-- 正在处理的任务 -->
            <div v-if="processingImport" class="processing-status">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>正在解析：{{ processingImport.source_file }}</span>
              <span v-if="processingImport.status === 'queued'" class="processing-detail">
                （排队等待中{{ processingImport.queue_position ? `，第 ${processingImport.queue_position} 位` : '' }}）
              </span>
              <span v-else-if="processingImport.total_rows > 0" class="processing-detail">
                （已处理 {{ processedCount }} / {{ processingImport.total_rows }} 行，{{ processingPercent }}%）
              </span>
              <span v-else class="processing-detail">
                （正在读取文件，请稍候...）
              </span>
              <el-tag :type="processingImport.status === 'queued' ? 'info' : 'primary'" size="small" class="processing-tag">
                {{ processingImport.status === 'queued' ? '排队中' : '处理中' }}
              </el-tag>
              <el-progress
                v-if="processingImport.total_rows > 0"
                :percentage="processingPercent"
                :stroke-width="6"
                :show-text="false"
                class="processing-progress"
              />
              <!-- total_rows 未知时显示不确定进度条 -->
              <el-progress
                v-else
                :percentage="0"
                :show-text="false"
                :stroke-width="6"
                class="processing-progress processing-progress--unknown"
              />
            </div>
          </el-card>

          <!-- 导入历史 -->
          <el-card class="section-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">导入历史</span>
                <el-button size="small" @click="loadImports" :loading="importsLoading">刷新</el-button>
              </div>
            </template>
            <el-table
              :data="importsList"
              size="small"
              v-loading="importsLoading"
              :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
            >
              <el-table-column prop="source_file" label="文件名" min-width="180" show-overflow-tooltip />
              <el-table-column prop="imported_at" label="导入时间" width="170" />
              <el-table-column label="排队" width="60" align="center">
                <template #default="{ row }">
                  <span v-if="row.queue_position" class="queue-pos">{{ row.queue_position }}</span>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="total_rows" label="总行数" width="75" align="center" />
              <el-table-column prop="rows_inserted" label="成功" width="60" align="center" />
              <el-table-column prop="rows_skipped" label="跳过" width="60" align="center">
                <template #header>
                  <el-tooltip content="内容完全重复（与已有告警或同批次其他Sheet重复），自动跳过" placement="top">
                    <span>跳过 <el-icon style="font-size:12px"><QuestionFilled /></el-icon></span>
                  </el-tooltip>
                </template>
              </el-table-column>
              <el-table-column prop="raw_rows" label="缺字段" width="65" align="center">
                <template #header>
                  <el-tooltip content="缺少必要字段（设备ID/源IP、外联目标、告警时间），无法入库" placement="top">
                    <span>缺字段 <el-icon style="font-size:12px"><QuestionFilled /></el-icon></span>
                  </el-tooltip>
                </template>
              </el-table-column>
              <el-table-column prop="rows_failed" label="失败" width="60" align="center">
                <template #header>
                  <el-tooltip content="解析过程中发生异常（如数据格式错误）" placement="top">
                    <span>失败 <el-icon style="font-size:12px"><QuestionFilled /></el-icon></span>
                  </el-tooltip>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="statusTagType(row.status)" :class="{ 'blink-tag': row.status === 'processing' }" size="small">
                    {{ statusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="260" align="center">
                <template #default="{ row }">
                  <el-button size="small" @click="showImportDetail(row)" :disabled="row.status === 'processing'">
                    查看详情
                  </el-button>
                  <el-button size="small" type="warning" @click="handleRepairMetadata(row)" :disabled="row.status === 'processing'">
                    修复元数据
                  </el-button>
                  <el-button size="small" type="danger" @click="handleDeleteImport(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 标签管理 -->
      <el-tab-pane label="标签管理" name="tags">
        <div class="tab-content">
          <!-- TXT 批量导入 -->
          <el-card class="section-card">
            <template #header>
              <span class="card-title">TXT 批量打标</span>
            </template>
            <p class="upload-hint mb-8">
              上传 01.排查成功的设备id.txt / 02.重点设备id.txt / 03.不好查设备id.txt，系统按文件名自动识别标签
            </p>
            <el-upload
              drag
              multiple
              :accept="'.txt'"
              :before-upload="beforeUploadTxt"
              :http-request="handleUploadTxt"
              :show-file-list="false"
            >
              <div class="upload-area">
                <el-icon class="upload-icon"><UploadFilled /></el-icon>
                <p>拖拽 .txt 文件到此处，或 <em>点击上传</em></p>
                <p class="upload-hint">支持同时上传多个 .txt 文件</p>
              </div>
            </el-upload>

            <!-- TXT 导入结果 -->
            <div v-if="txtImportResult" class="import-result">
              <el-alert :title="txtImportResult.success ? 'TXT导入成功' : 'TXT导入失败'" :type="txtImportResult.success ? 'success' : 'error'" show-icon :closable="true" @close="txtImportResult = null">
                <div v-if="txtImportResult.success">
                  <template v-for="item in txtImportResult.items" :key="item.batch_name">
                    <div>{{ item.batch_name }}：标签「{{ item.tag_name }}」，导入 {{ item.device_count }} 台设备</div>
                  </template>
                </div>
                <div v-else>{{ txtImportResult.message }}</div>
              </el-alert>
            </div>
          </el-card>

          <!-- 批量设备打标 -->
          <el-card class="section-card">
            <template #header>
              <span class="card-title">批量设备打标 / 删标</span>
            </template>
            <p class="upload-hint mb-8">
              粘贴设备ID列表（每行一个），然后选择标签进行批量添加或删除
            </p>
            <el-input
              v-model="batchDeviceText"
              type="textarea"
              :rows="8"
              placeholder="粘贴设备ID，每行一个&#10;例如：&#10;SRV-HZ-618&#10;LAPTOP-WH-819&#10;WS-huangshan67"
              class="batch-device-input"
            />
            <div class="batch-tag-actions">
              <el-button type="primary" size="small" @click="showBatchAddTagDialog" :disabled="!batchDeviceText.trim()">
                <el-icon><Plus /></el-icon>
                添加标签
              </el-button>
              <el-button type="danger" size="small" @click="showBatchRemoveTagDialog" :disabled="!batchDeviceText.trim()">
                <el-icon><Delete /></el-icon>
                删除标签
              </el-button>
              <el-button size="small" @click="batchDeviceText = ''">清空</el-button>
            </div>
          </el-card>

          <!-- 批量添加标签对话框 -->
          <el-dialog v-model="batchAddDialogVisible" title="批量添加标签" width="420px">
            <el-form :model="batchAddForm" label-width="80px">
              <el-form-item label="标签名" required>
                <el-select
                  v-model="batchAddForm.tag_name"
                  filterable
                  allow-create
                  default-first-option
                  placeholder="选择或输入新标签名"
                  class="batch-tag-select"
                >
                  <el-option
                    v-for="tag in existingTagNames"
                    :key="tag"
                    :label="tag"
                    :value="tag"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="颜色">
                <el-color-picker v-model="batchAddForm.color" size="small" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="batchAddDialogVisible = false">取消</el-button>
              <el-button type="primary" @click="confirmBatchAddTag" :loading="batchSaving">
                确认添加 ({{ batchDeviceCount }} 台设备)
              </el-button>
            </template>
          </el-dialog>

          <!-- 批量删除标签对话框 -->
          <el-dialog v-model="batchRemoveDialogVisible" title="批量删除标签" width="420px">
            <el-form :model="batchRemoveForm" label-width="80px">
              <el-form-item label="选择标签" required>
                <el-select
                  v-model="batchRemoveForm.tag_id"
                  placeholder="选择要删除的标签"
                  class="batch-tag-select"
                >
                  <el-option
                    v-for="tag in existingTags"
                    :key="tag.id"
                    :label="tag.name"
                    :value="tag.id"
                  />
                </el-select>
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="batchRemoveDialogVisible = false">取消</el-button>
              <el-button type="danger" @click="confirmBatchRemoveTag" :loading="batchSaving">
                确认删除 ({{ batchDeviceCount }} 台设备)
              </el-button>
            </template>
          </el-dialog>

          <!-- 标签批次记录 -->
          <el-card class="section-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">标签批次记录</span>
                <el-button size="small" @click="loadBatches" :loading="batchesLoading">刷新</el-button>
              </div>
            </template>
            <el-table
              :data="batchesList"
              size="small"
              v-loading="batchesLoading"
              :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
            >
              <el-table-column prop="batch_name" label="批次名" min-width="150" show-overflow-tooltip />
              <el-table-column prop="tag_name" label="标签名" width="120">
                <template #default="{ row }">
                  <el-tag :color="row.color" :style="{ color: '#fff', border: 'none' }" size="small">{{ row.tag_name }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="device_count" label="设备数" width="80" align="center" />
              <el-table-column prop="created_at" label="创建时间" width="170" />
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'deleted' ? 'danger' : 'success'" size="small">
                    {{ row.status === 'deleted' ? '已删除' : '活跃' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
              <el-table-column label="操作" width="260" align="center">
                <template #default="{ row }">
                  <el-button size="small" @click="showBatchDetail(row)">详情</el-button>
                  <el-button size="small" type="success" @click="handleRestoreBatch(row)">一键恢复</el-button>
                  <el-button size="small" type="danger" @click="handleDeleteBatch(row)" :disabled="row.status === 'deleted'">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 标签颜色管理 -->
          <el-card class="section-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">标签颜色管理</span>
                <el-button size="small" @click="loadAllTags" :loading="allTagsLoading">刷新</el-button>
              </div>
            </template>
            <p class="upload-hint mb-8">修改已存在标签的名称和颜色，即时生效。</p>
            <el-table
              :data="allTagsList"
              size="small"
              v-loading="allTagsLoading"
              :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
            >
              <el-table-column label="ID" width="60" align="center" prop="id" />
              <el-table-column label="标签名" min-width="140">
                <template #default="{ row }">
                  <el-input
                    v-model="row._editName"
                    size="small"
                    :disabled="!row._editing"
                  />
                </template>
              </el-table-column>
              <el-table-column label="颜色" width="100" align="center">
                <template #default="{ row }">
                  <el-color-picker
                    v-model="row._editColor"
                    size="small"
                    :disabled="!row._editing"
                  />
                </template>
              </el-table-column>
              <el-table-column label="预览" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :color="row._editColor" :style="{ color: '#fff', border: 'none' }" size="small">
                    {{ row._editName || row.name }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="创建时间" width="170" prop="created_at" />
              <el-table-column label="操作" width="140" align="center">
                <template #default="{ row }">
                  <template v-if="!row._editing">
                    <el-button size="small" type="primary" @click="startEditTag(row)">编辑</el-button>
                  </template>
                  <template v-else>
                    <el-button size="small" @click="cancelEditTag(row)">取消</el-button>
                    <el-button size="small" type="primary" @click="saveEditTag(row)" :loading="row._saving">保存</el-button>
                  </template>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 追踪库 -->
          <el-card class="section-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">追踪库</span>
                <div>
                  <el-button size="small" type="primary" @click="addTracedDialogVisible = true">手动添加</el-button>
                  <el-button size="small" @click="loadTraced" :loading="tracedLoading">刷新</el-button>
                </div>
              </div>
            </template>

            <!-- 追踪库Excel导入 -->
            <div class="traced-upload-row">
              <el-upload
                :accept="'.xlsx,.xls'"
                :before-upload="beforeUploadTraced"
                :http-request="handleUploadTraced"
                :show-file-list="false"
              >
                <el-button size="small">
                  <el-icon><Upload /></el-icon>
                  导入追踪库Excel
                </el-button>
              </el-upload>
            </div>

            <el-table
              :data="tracedList"
              size="small"
              v-loading="tracedLoading"
              :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
              class="mt-12"
            >
              <el-table-column prop="target" label="目标" min-width="200" show-overflow-tooltip />
              <el-table-column prop="port" label="端口" width="80" align="center" />
              <el-table-column prop="note" label="备注" min-width="150" show-overflow-tooltip />
              <el-table-column prop="traced_at" label="添加时间" width="170" />
              <el-table-column label="操作" width="80" align="center">
                <template #default="{ row }">
                  <el-button size="small" type="danger" @click="handleDeleteTraced(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 系统设置 -->
      <el-tab-pane label="系统设置" name="config">
        <div class="tab-content">
          <el-card class="section-card">
            <template #header>
              <span class="card-title">基础配置</span>
            </template>
            <el-form :model="configForm" label-width="140px" class="config-form">
              <el-form-item label="追踪 TTL 天数">
                <el-input-number
                  v-model="configForm.trace_ttl_days"
                  :min="1"
                  :max="3650"
                  controls-position="right"
                />
              </el-form-item>
              <el-form-item label="默认隐藏已追踪">
                <el-switch v-model="configForm.default_hide_traced" />
              </el-form-item>
              <el-form-item label="默认隐藏已关闭事件">
                <el-switch v-model="configForm.default_hide_closed" />
              </el-form-item>
              <el-form-item label="Badge 显示">
                <el-checkbox-group v-model="configForm.badges">
                  <el-checkbox v-for="b in badgeOptions" :key="b.id" :label="b.id" :value="b.id">
                    {{ b.label }}
                  </el-checkbox>
                </el-checkbox-group>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleSaveConfig" :loading="configSaving">保存配置</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 表格列设置 -->
          <el-card class="section-card">
            <template #header>
              <span class="card-title">工作台表格列设置</span>
            </template>
            <p class="upload-hint mb-8">
              设置研判工作台表格的默认显示列和排序。变更即时生效，自动记忆。
            </p>
            <el-table
              :data="columnSettings"
              size="small"
              :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
            >
              <el-table-column label="排序" width="80" align="center">
                <template #default="{ $index }">
                  <el-button-group size="small">
                    <el-button
                      :disabled="$index === 0"
                      size="small"
                      @click="moveColumn($index, -1)"
                    >
                      <el-icon><ArrowUp /></el-icon>
                    </el-button>
                    <el-button
                      :disabled="$index === columnSettings.length - 1"
                      size="small"
                      @click="moveColumn($index, 1)"
                    >
                      <el-icon><ArrowDown /></el-icon>
                    </el-button>
                  </el-button-group>
                </template>
              </el-table-column>
              <el-table-column prop="label" label="列名" min-width="140" />
              <el-table-column label="显示" width="80" align="center">
                <template #default="{ row }">
                  <el-switch
                    :model-value="row.visible"
                    @change="toggleColumnSetting(row.key)"
                    size="small"
                  />
                </template>
              </el-table-column>
            </el-table>
            <div class="column-settings-actions">
              <el-button
                type="primary"
                size="small"
                :disabled="!hasPendingColumnChanges"
                @click="handleSaveColumnSettings"
              >
                保存当前设置
              </el-button>
            </div>
          </el-card>

          <el-card class="section-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">词典管理</span>
                <el-button size="small" @click="loadDicts" :loading="dictsLoading">刷新</el-button>
              </div>
            </template>
            <div v-loading="dictsLoading" class="dicts-display">
              <template v-if="dicts">
                <div v-for="(content, name) in dicts" :key="name" class="dict-section">
                  <h4 class="dict-name">{{ dictDisplayName(name) }}</h4>
                  <pre class="dict-content">{{ content }}</pre>
                </div>
              </template>
              <el-empty v-else description="暂无词典数据" />
            </div>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 系统信息 -->
      <el-tab-pane label="系统信息" name="system">
        <div class="tab-content">
          <!-- 版本信息卡片 -->
          <el-card class="section-card">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">版本信息</span>
                <el-button size="small" @click="checkUpdate" :loading="versionChecking">
                  <el-icon><Refresh /></el-icon>
                  检查更新
                </el-button>
              </div>
            </template>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="当前版本">
                <el-tag type="primary" size="small">v{{ versionInfo.version }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="Git Commit">
                <span v-if="versionInfo.git_commit" class="commit-hash">{{ versionInfo.git_commit }}</span>
                <span v-else class="text-muted">未初始化</span>
              </el-descriptions-item>
              <el-descriptions-item label="远程仓库" :span="2">
                <span v-if="versionInfo.git_remote_url" class="remote-url">{{ versionInfo.git_remote_url }}</span>
                <span v-else class="text-muted">未配置</span>
              </el-descriptions-item>
              <el-descriptions-item label="更新状态" :span="2">
                <el-tag v-if="versionInfo.update_available" type="warning" size="small">有新版本可用</el-tag>
                <el-tag v-else-if="versionInfo.local_ahead" type="info" size="small">本地领先于远程</el-tag>
                <el-tag v-else-if="versionInfo.is_git_repo" type="success" size="small">已是最新版本</el-tag>
                <el-tag v-else type="info" size="small">未使用 Git 管理</el-tag>
              </el-descriptions-item>
            </el-descriptions>
            <div class="system-actions">
              <el-button type="primary" size="small" @click="goToUpdate">
                更新代码
              </el-button>
              <span class="update-hint">更新代码后启动平台，数据库将自动迁移</span>
            </div>
          </el-card>

          <!-- 变更日志卡片 -->
          <el-card class="section-card">
            <template #header>
              <span class="card-title">变更日志</span>
            </template>
            <div v-loading="changelogLoading" class="changelog-content">
              <pre v-if="changelog">{{ changelog }}</pre>
              <el-empty v-else description="暂无变更日志" />
            </div>
          </el-card>

          <!-- 数据管理 -->
          <el-card class="section-card">
            <template #header>
              <span class="card-title">数据管理</span>
            </template>
            <div class="data-management">
              <el-button size="small" @click="openBackupsDir">
                <el-icon><FolderOpened /></el-icon>
                打开备份目录
              </el-button>
              <span class="data-hint">数据库备份位于 backups/ 目录</span>
            </div>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 导入详情 Dialog -->
    <el-dialog v-model="importDetailVisible" title="导入详情" width="900px" @opened="onImportDetailOpened">
      <div v-if="importDetail" class="import-detail">
        <!-- 汇总统计卡片 -->
        <div class="import-stats-row">
          <div class="stat-card stat-total">
            <span class="stat-num">{{ importDetail.total_rows }}</span>
            <span class="stat-label">总行数</span>
          </div>
          <div class="stat-card stat-success">
            <span class="stat-num">{{ importDetail.rows_inserted }}</span>
            <span class="stat-label">成功导入</span>
          </div>
          <div class="stat-card stat-skipped">
            <span class="stat-num">{{ importDetail.rows_skipped }}</span>
            <span class="stat-label">跳过(重复)</span>
            <el-tooltip content="设备、时间、目标、端口等关键字段完全一致时，自动跳过避免重复入库" placement="top">
              <el-icon class="stat-help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="stat-card stat-raw">
            <span class="stat-num">{{ importDetail.raw_rows || 0 }}</span>
            <span class="stat-label">缺少字段</span>
            <el-tooltip content="缺少必要字段（设备ID/源IP、外联目标、告警时间），无法解析入库" placement="top">
              <el-icon class="stat-help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div class="stat-card stat-failed">
            <span class="stat-num">{{ importDetail.rows_failed }}</span>
            <span class="stat-label">解析失败</span>
            <el-tooltip content="数据解析过程中发生异常错误" placement="top">
              <el-icon class="stat-help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
        </div>

        <div class="import-meta">
          <span><strong>文件：</strong>{{ importDetail.source_file }}</span>
          <span><strong>状态：</strong><el-tag :type="statusTagType(importDetail.status)" size="small">{{ statusLabel(importDetail.status) }}</el-tag></span>
        </div>

        <!-- Sheet 列表 -->
        <div class="detail-section">
          <h4 class="detail-section-title">Sheet 列表</h4>
          <el-table
            :data="importSheets"
            size="small"
            v-loading="sheetsLoading"
            :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
          >
            <el-table-column prop="sheet_name" label="Sheet 名" min-width="200" />
            <el-table-column prop="row_count" label="总行数" width="100" align="center" />
            <el-table-column prop="parsed_rows" label="成功" width="80" align="center" />
            <el-table-column prop="raw_rows" label="缺字段" width="80" align="center" />
            <el-table-column prop="failed_rows" label="失败" width="80" align="center" />
          </el-table>
        </div>

        <!-- 行级明细 -->
        <div class="detail-section">
          <div class="detail-section-header">
            <h4 class="detail-section-title">问题明细</h4>
          </div>

          <div class="detail-subsection">
            <div class="detail-section-header">
              <h5 class="detail-subsection-title">失败 / 缺少字段</h5>
              <div class="detail-section-actions">
                <el-button size="small" @click="loadIssueRows" :loading="rowsLoading.issue">刷新</el-button>
                <el-button size="small" @click="handleDownloadRows('failures')" :disabled="issueCount === 0">
                  下载 CSV
                </el-button>
              </div>
            </div>
            <el-table
              :data="issueRows"
              size="small"
              v-loading="rowsLoading.issue"
              :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
            >
              <el-table-column prop="excel_row_number" label="行号" width="70" align="center" />
              <el-table-column prop="sheet_name" label="Sheet" width="120" show-overflow-tooltip />
              <el-table-column label="状态" width="110" align="center">
                <template #default="{ row }">
                  <el-tag :type="rowStatusTag(row.parse_status)" size="small">
                    {{ rowStatusLabel(row.parse_status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="parse_error" label="原因" min-width="260" show-overflow-tooltip>
                <template #default="{ row }">
                  <span v-if="row.parse_error" class="error-text">{{ row.parse_error }}</span>
                  <span v-else class="no-error-text">-</span>
                </template>
              </el-table-column>
              <el-table-column label="关键列" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ issueSummary(row) }}
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div class="detail-subsection">
            <div class="detail-section-header">
              <h5 class="detail-subsection-title">跳过重复</h5>
              <div class="detail-section-actions">
                <el-button size="small" @click="loadSkippedRows" :loading="rowsLoading.skipped">刷新</el-button>
                <el-button size="small" @click="handleDownloadRows('skipped')" :disabled="skippedCount === 0">
                  下载 CSV
                </el-button>
              </div>
            </div>
            <el-table
              :data="skippedRows"
              size="small"
              v-loading="rowsLoading.skipped"
              :header-cell-style="{ background: 'var(--table-header-bg)', color: 'var(--table-header-text)', borderColor: 'var(--border-color)' }"
            >
              <el-table-column prop="excel_row_number" label="行号" width="70" align="center" />
              <el-table-column prop="sheet_name" label="Sheet" width="120" show-overflow-tooltip />
              <el-table-column label="设备ID" min-width="140" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ getRowValue(row, 'device_id', ['设备ID', '设备 ID']) || '-' }}
                </template>
              </el-table-column>
              <el-table-column label="外联目标" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ getRowValue(row, 'target', ['外联目标', '目标']) || '-' }}
                </template>
              </el-table-column>
              <el-table-column label="端口" width="90" align="center">
                <template #default="{ row }">
                  {{ getRowValue(row, 'port', ['外联端口', '端口']) || '-' }}
                </template>
              </el-table-column>
              <el-table-column label="原因" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">
                  {{ skippedReason(row) }}
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 手动添加追踪 Dialog -->
    <el-dialog v-model="addTracedDialogVisible" title="手动添加追踪" width="450px">
      <el-form :model="addTracedForm" label-width="60px">
        <el-form-item label="目标" required>
          <el-input v-model="addTracedForm.target" placeholder="IP 或域名" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input v-model="addTracedForm.port" placeholder="可选" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="addTracedForm.note" type="textarea" :rows="2" placeholder="可选备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addTracedDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddTraced" :loading="tracedSaving">添加</el-button>
      </template>
    </el-dialog>

    <!-- 批次详情 Dialog -->
    <el-dialog v-model="batchDetailVisible" title="批次详情" width="650px">
      <div v-if="batchDetail" class="batch-detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="批次名">{{ batchDetail.batch_name }}</el-descriptions-item>
          <el-descriptions-item label="标签名">
            <el-tag :color="batchDetail.color" :style="{ color: '#fff', border: 'none' }" size="small">
              {{ batchDetail.tag_name }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="设备数">{{ batchDetail.device_count }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="batchDetail.status === 'deleted' ? 'danger' : 'success'" size="small">
              {{ batchDetail.status === 'deleted' ? '已删除' : '活跃' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ batchDetail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="备注" :span="2">{{ batchDetail.note || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="batch-device-header">
          <span class="card-title">设备列表（{{ batchDetail.devices ? batchDetail.devices.length : 0 }} 台）</span>
          <el-button size="small" type="danger" @click="showBatchPartialRemove" :disabled="!batchDetail.devices || batchDetail.devices.length === 0">
            部分删除
          </el-button>
        </div>
        <el-input
          v-if="batchDetail.devices && batchDetail.devices.length > 0"
          type="textarea"
          :rows="Math.min(12, batchDetail.devices.length)"
          :model-value="batchDetail.devices.join('\n')"
          readonly
          class="batch-device-list"
        />
        <el-empty v-else description="暂无设备" :image-size="60" />
      </div>
    </el-dialog>

    <!-- 批次部分删除 Dialog -->
    <el-dialog v-model="partialRemoveVisible" title="部分删除设备" width="500px">
      <p class="upload-hint mb-8">
        在下方文本框中删除不需要的设备ID行，保留需要继续打标的设备。修改后的设备列表将替换原批次。
      </p>
      <el-input
        v-model="partialRemoveDevices"
        type="textarea"
        :rows="12"
        placeholder="每行一个设备ID"
      />
      <template #footer>
        <el-button @click="partialRemoveVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmPartialRemove" :loading="batchSaving">
          确认删除（删除 {{ partialRemoveOriginalCount - partialRemoveDevices.split(/[\n\r]+/).map(s => s.trim()).filter(Boolean).length }} 台设备）
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { UploadFilled, Upload, Loading, Plus, Delete, ArrowUp, ArrowDown, QuestionFilled, Refresh, FolderOpened } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  uploadExcel, fetchImports, fetchImport, fetchImportSheets, fetchImportRows, downloadImportRowsCsv, deleteImport, repairImportMetadata
} from '../api/imports'
import {
  importTextFiles, fetchBatches, fetchBatch, deleteBatch, removeDevicesFromBatch,
  restoreBatch, batchAddDeviceTag, batchRemoveDeviceTag, fetchTags, updateTag
} from '../api/tags'
import {
  importTraced, fetchTracedList, deleteTraced, createTraced
} from '../api/traced'
import {
  fetchConfig, saveConfig, fetchDicts
} from '../api/config'
import { fetchVersion } from '../api/version'
import { useColumnConfig, saveColumnOrder } from '../composables/useColumnConfig'

// Tab 切换
const activeTab = ref('import')

// ====== Tab 1: 数据导入 ======

const importsList = ref([])
const importsLoading = ref(false)
const processingImport = ref(null)
let importPollTimer = null

// Upload progress state
const uploadProgress = ref(0)
const uploadingFileName = ref('')

function statusLabel(status) {
  const map = { success: '成功', partial: '部分成功', failed: '失败', processing: '处理中', queued: '排队中' }
  return map[status] || status || '-'
}

function statusTagType(status) {
  const map = { success: 'success', partial: 'warning', failed: 'danger', processing: 'primary', queued: 'info' }
  return map[status] || 'info'
}

// Processing progress: raw_rows tracks parsed-so-far during processing,
// then becomes the final 'rows with missing fields' count after completion.
const processedCount = computed(() => {
  const p = processingImport.value
  if (!p) return 0
  return (p.rows_inserted || 0) + (p.rows_skipped || 0) + (p.rows_failed || 0) + (p.raw_rows || 0)
})

const processingPercent = computed(() => {
  const p = processingImport.value
  if (!p || !p.total_rows) return 0
  return Math.min(100, Math.round(processedCount.value / p.total_rows * 100))
})

async function loadImports() {
  importsLoading.value = true
  try {
    const res = await fetchImports()
    const list = Array.isArray(res) ? res : (res.items || [])
    importsList.value = list

    // 检查是否有正在处理的任务（queued/processing/uploaded 都表示处理中）
    const processing = list.find(i => i.status === 'queued' || i.status === 'processing' || i.status === 'uploaded')
    if (processing) {
      processingImport.value = processing
      startImportPolling(processing.id)
    } else {
      processingImport.value = null
      stopImportPolling()
    }
  } catch (e) {
    ElMessage.error('加载导入历史失败: ' + e.message)
  } finally {
    importsLoading.value = false
  }
}

function startImportPolling(id) {
  stopImportPolling()
  importPollTimer = setInterval(async () => {
    try {
      const detail = await fetchImport(id)
      if (detail.status !== 'queued' && detail.status !== 'processing' && detail.status !== 'uploaded') {
        processingImport.value = null
        stopImportPolling()
        loadImports()
        ElMessage.success('导入完成：' + detail.source_file)
      } else {
        processingImport.value = detail
      }
    } catch {
      // 轮询失败不报错，继续尝试
    }
  }, 3000)
}

function stopImportPolling() {
  if (importPollTimer) {
    clearInterval(importPollTimer)
    importPollTimer = null
  }
}

function beforeUploadExcel(file) {
  const isExcel = file.name.endsWith('.xlsx') || file.name.endsWith('.xls')
  if (!isExcel) {
    ElMessage.error('只支持 .xlsx / .xls 文件')
    return false
  }
  return true
}

async function handleUploadExcel({ file }) {
  uploadProgress.value = 0
  uploadingFileName.value = file.name
  try {
    const result = await uploadExcel([file], (pct) => {
      uploadProgress.value = pct
    })
    uploadProgress.value = 100
    // 立即显示处理状态，不要等 loadImports 轮询才显示
    const jobs = result?.jobs || []
    if (jobs.length > 0) {
      const job = jobs[0]
      if (job.duplicate) {
        // 文件已经上传过，直接提示
        ElMessage.info('该文件已上传过（' + job.source_file + '），已跳过重复导入。')
        loadImports()
      } else {
        processingImport.value = {
          source_file: job.source_file,
          status: job.status || 'queued',
          total_rows: 0,
          rows_inserted: 0,
          rows_skipped: 0,
          rows_failed: 0,
          raw_rows: 0,
        }
        if (job.status === 'queued') {
          processingImport.value.queue_position = job.queue_position
        }
        startImportPolling(job.id)
        if (job.status === 'queued') {
          ElMessage.success('文件已接收，正在排队等待处理：' + file.name)
        } else {
          ElMessage.success('文件已接收，正在解析：' + file.name)
        }
      }
    }
  } catch (e) {
    // 超时不代表失败——后端可能已经在处理了
    const isTimeout = e.message?.includes('timeout') || e.message?.includes('time')
    if (isTimeout) {
      ElMessage.warning('上传时间较长，文件可能已在后台处理。请查看导入历史确认。')
      loadImports()
    } else {
      ElMessage.error('上传失败: ' + e.message)
    }
  } finally {
    // 上传进度条立即消失
    uploadProgress.value = 0
    uploadingFileName.value = ''
    // 重新加载导入历史（重复文件的情况也在这里显示）
    loadImports()
  }
}

// 导入详情
const importDetailVisible = ref(false)
const importDetail = ref(null)
const importSheets = ref([])
const sheetsLoading = ref(false)

// 行明细
const issueRows = ref([])
const skippedRows = ref([])
const rowsLoading = ref({ issue: false, skipped: false })
const issueCount = ref(0)
const skippedCount = ref(0)

function rowStatusLabel(status) {
  const map = {
    parsed: '成功',
    skipped_duplicate: '跳过(重复)',
    raw_only: '缺少字段',
    failed: '失败',
  }
  return map[status] || status || '-'
}

function rowStatusTag(status) {
  const map = {
    parsed: 'success',
    skipped_duplicate: 'info',
    raw_only: 'warning',
    failed: 'danger',
  }
  return map[status] || 'info'
}

function getRowValue(row, normalizedKey, rawKeys = []) {
  const normalized = row?.normalized || {}
  const raw = row?.raw || {}
  const normalizedValue = normalized[normalizedKey]
  if (normalizedValue !== undefined && normalizedValue !== null && normalizedValue !== '') {
    return normalizedValue
  }
  for (const key of rawKeys) {
    const rawValue = raw[key]
    if (rawValue !== undefined && rawValue !== null && rawValue !== '') {
      return rawValue
    }
  }
  return ''
}

function issueSummary(row) {
  const deviceId = getRowValue(row, 'device_id', ['设备ID', '设备 ID']) || '-'
  const target = getRowValue(row, 'target', ['外联目标', '目标']) || '-'
  const port = getRowValue(row, 'port', ['外联端口', '端口']) || '-'
  return `设备ID: ${deviceId} | 目标: ${target} | 端口: ${port}`
}

function skippedReason(row) {
  return row.parse_error || '与已导入记录关键字段（含时间）完全一致，已自动跳过'
}

async function loadIssueRows() {
  if (!importDetail.value) return
  rowsLoading.value.issue = true
  try {
    const res = await fetchImportRows(importDetail.value.id, { status_group: 'issues', page: 1, page_size: 300 })
    issueRows.value = res.items || []
    issueCount.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载行明细失败: ' + e.message)
    issueRows.value = []
  } finally {
    rowsLoading.value.issue = false
  }
}

async function loadSkippedRows() {
  if (!importDetail.value) return
  rowsLoading.value.skipped = true
  try {
    const res = await fetchImportRows(importDetail.value.id, { status_group: 'skipped', page: 1, page_size: 300 })
    skippedRows.value = res.items || []
    skippedCount.value = res.total || 0
  } catch (e) {
    ElMessage.error('加载跳过明细失败: ' + e.message)
    skippedRows.value = []
  } finally {
    rowsLoading.value.skipped = false
  }
}

function onImportDetailOpened() {
  loadIssueRows()
  loadSkippedRows()
}

async function handleDownloadRows(type) {
  if (!importDetail.value) return
  try {
    const blob = await downloadImportRowsCsv(importDetail.value.id, type)
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `import_${importDetail.value.id}_${type}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    ElMessage.success('CSV 下载已开始')
  } catch (e) {
    ElMessage.error('下载失败: ' + e.message)
  }
}

async function showImportDetail(row) {
  importDetail.value = row
  importDetailVisible.value = true
  sheetsLoading.value = true
  issueRows.value = []
  skippedRows.value = []
  issueCount.value = 0
  skippedCount.value = 0
  try {
    importSheets.value = await fetchImportSheets(row.id)
  } catch (e) {
    ElMessage.error('加载Sheet列表失败: ' + e.message)
    importSheets.value = []
  } finally {
    sheetsLoading.value = false
  }
}

async function handleDeleteImport(row) {
  try {
    await ElMessageBox.confirm(`确定删除导入记录「${row.source_file}」？关联的告警数据也会被删除。`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteImport(row.id)
    ElMessage.success('删除成功')
    loadImports()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败: ' + e.message)
    }
  }
}

async function handleRepairMetadata(row) {
  try {
    await ElMessageBox.confirm(
      `将从导入记录「${row.source_file}」的原始数据中重新提取元数据字段（研判状态、重点关注），修复此前因解析逻辑不完整导致的字段缺失。该操作不会重复导入，仅更新已有数据。`,
      '确认修复',
      {
        confirmButtonText: '修复',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    const res = await repairImportMetadata(row.id)
    const stats = res.stats || {}
    ElMessage.success(`修复完成：共 ${stats.total} 条，修复 ${stats.repaired} 条，跳过 ${stats.skipped} 条，错误 ${stats.errors} 条`)
    loadImports()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('修复失败: ' + e.message)
    }
  }
}

// ====== Tab 2: 标签管理 ======

// TXT 导入
const txtImportResult = ref(null)

function beforeUploadTxt(file) {
  if (!file.name.endsWith('.txt')) {
    ElMessage.error('只支持 .txt 文件')
    return false
  }
  return true
}

async function handleUploadTxt({ file }) {
  try {
    const result = await importTextFiles([file])
    const items = Array.isArray(result?.imported) ? result.imported : []
    txtImportResult.value = {
      success: true,
      items: items.map(item => ({
        batch_name: item.batch_name || file.name.replace('.txt', ''),
        tag_name: item.tag_name || '未命名',
        device_count: item.device_count || 0,
      })),
    }
    loadBatches()
  } catch (e) {
    txtImportResult.value = { success: false, message: e.message }
  }
}

// 批量设备打标 / 删标
const batchDeviceText = ref('')
const batchAddDialogVisible = ref(false)
const batchRemoveDialogVisible = ref(false)
const batchAddForm = ref({ tag_name: '', color: '#409EFF' })
const batchRemoveForm = ref({ tag_id: null })
const batchSaving = ref(false)
const existingTags = ref([])

const existingTagNames = computed(() => existingTags.value.map(t => t.name).filter(Boolean))
const batchDeviceCount = computed(() => batchDeviceText.value.split(/[\n\r]+/).map(s => s.trim()).filter(Boolean).length)

function parseBatchDeviceIds() {
  return batchDeviceText.value.split(/[\n\r]+/).map(s => s.trim()).filter(Boolean)
}

async function loadExistingTags() {
  try {
    const res = await fetchTags()
    existingTags.value = Array.isArray(res) ? res : []
  } catch (e) { /* silent */ }
}

function showBatchAddTagDialog() {
  batchAddForm.value = { tag_name: '', color: '#409EFF' }
  loadExistingTags()
  batchAddDialogVisible.value = true
}

function showBatchRemoveTagDialog() {
  batchRemoveForm.value = { tag_id: null }
  loadExistingTags()
  batchRemoveDialogVisible.value = true
}

async function confirmBatchAddTag() {
  if (!batchAddForm.value.tag_name) {
    ElMessage.warning('标签名不能为空')
    return
  }
  const devices = parseBatchDeviceIds()
  if (devices.length === 0) {
    ElMessage.warning('请至少输入一个设备ID')
    return
  }
  batchSaving.value = true
  try {
    const res = await batchAddDeviceTag({
      devices,
      tag_name: batchAddForm.value.tag_name,
      color: batchAddForm.value.color,
    })
    ElMessage.success(`成功为 ${res.device_count} 台设备添加标签「${res.tag_name}」`)
    batchAddDialogVisible.value = false
    loadBatches()
  } catch (e) {
    ElMessage.error('批量添加标签失败: ' + e.message)
  } finally {
    batchSaving.value = false
  }
}

async function confirmBatchRemoveTag() {
  if (!batchRemoveForm.value.tag_id) {
    ElMessage.warning('请选择要删除的标签')
    return
  }
  const devices = parseBatchDeviceIds()
  if (devices.length === 0) {
    ElMessage.warning('请至少输入一个设备ID')
    return
  }
  batchSaving.value = true
  try {
    const res = await batchRemoveDeviceTag({
      devices,
      tag_id: batchRemoveForm.value.tag_id,
    })
    ElMessage.success(`成功从 ${res.removed_count} 台设备删除标签`)
    batchRemoveDialogVisible.value = false
    loadBatches()
  } catch (e) {
    ElMessage.error('批量删除标签失败: ' + e.message)
  } finally {
    batchSaving.value = false
  }
}

// 批次记录
const batchesList = ref([])
const batchesLoading = ref(false)

async function loadBatches() {
  batchesLoading.value = true
  try {
    const res = await fetchBatches()
    batchesList.value = Array.isArray(res) ? res : (res.items || [])
  } catch (e) {
    ElMessage.error('加载批次列表失败: ' + e.message)
  } finally {
    batchesLoading.value = false
  }
}

async function handleDeleteBatch(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除批次「${row.batch_name}」？批次将被标记为"已删除"，不会移除关联的标签和设备。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await deleteBatch(row.id)
    ElMessage.success('批次已标记为已删除')
    loadBatches()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败: ' + e.message)
    }
  }
}

// 批次详情
const batchDetailVisible = ref(false)
const batchDetail = ref(null)

async function showBatchDetail(row) {
  batchDetailVisible.value = true
  batchDetail.value = null
  try {
    batchDetail.value = await fetchBatch(row.id)
  } catch (e) {
    ElMessage.error('加载批次详情失败: ' + e.message)
    batchDetailVisible.value = false
  }
}

// 批次部分删除
const partialRemoveVisible = ref(false)
const partialRemoveDevices = ref('')
const partialRemoveBatchId = ref(null)
const partialRemoveOriginalCount = ref(0)

function showBatchPartialRemove() {
  if (!batchDetail.value || !batchDetail.value.devices) return
  partialRemoveBatchId.value = batchDetail.value.id
  partialRemoveDevices.value = batchDetail.value.devices.join('\n')
  partialRemoveOriginalCount.value = batchDetail.value.devices.length
  partialRemoveVisible.value = true
}

async function confirmPartialRemove() {
  const currentDevices = partialRemoveDevices.value
    .split(/[\n\r]+/)
    .map(s => s.trim())
    .filter(Boolean)
  const originalDevices = batchDetail.value.devices || []
  const removedDevices = originalDevices.filter(d => !currentDevices.includes(d))

  if (removedDevices.length === 0) {
    ElMessage.warning('没有设备被移除')
    return
  }

  batchSaving.value = true
  try {
    const res = await removeDevicesFromBatch(partialRemoveBatchId.value, removedDevices)
    ElMessage.success(`已从批次中移除 ${res.removed_count} 台设备`)
    partialRemoveVisible.value = false
    // Refresh batch detail
    batchDetail.value = await fetchBatch(batchDetail.value.id)
    loadBatches()
  } catch (e) {
    ElMessage.error('部分删除失败: ' + e.message)
  } finally {
    batchSaving.value = false
  }
}

// 批次一键恢复
async function handleRestoreBatch(row) {
  try {
    const isDeleted = row.status === 'deleted'
    await ElMessageBox.confirm(
      isDeleted
        ? `确定恢复已删除的批次「${row.batch_name}」？将恢复批次状态并重新为所有关联设备打上标签。`
        : `确定恢复批次「${row.batch_name}」？将重新为所有关联设备打上标签。`,
      '确认恢复',
      {
        confirmButtonText: '恢复',
        cancelButtonText: '取消',
        type: 'info',
      }
    )
    const res = await restoreBatch(row.id)
    ElMessage.success(`批次已恢复，重新打标 ${res.restored_count} 条`)
    loadBatches()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('恢复失败: ' + e.message)
    }
  }
}

// ====== 标签颜色管理 ======
const allTagsList = ref([])
const allTagsLoading = ref(false)

async function loadAllTags() {
  allTagsLoading.value = true
  try {
    const res = await fetchTags()
    allTagsList.value = (Array.isArray(res) ? res : []).map(t => ({
      ...t,
      _editName: t.name,
      _editColor: t.color || '#409EFF',
      _editing: false,
      _saving: false,
    }))
  } catch (e) {
    ElMessage.error('加载标签列表失败: ' + e.message)
  } finally {
    allTagsLoading.value = false
  }
}

function startEditTag(row) {
  row._editing = true
  row._editName = row.name
  row._editColor = row.color || '#409EFF'
}

function cancelEditTag(row) {
  row._editing = false
  row._editName = row.name
  row._editColor = row.color || '#409EFF'
}

async function saveEditTag(row) {
  if (!row._editName || !row._editName.trim()) {
    ElMessage.warning('标签名不能为空')
    return
  }
  row._saving = true
  try {
    await updateTag(row.id, {
      name: row._editName.trim(),
      color: row._editColor,
    })
    row.name = row._editName.trim()
    row.color = row._editColor
    row._editing = false
    ElMessage.success('标签已更新')
  } catch (e) {
    ElMessage.error('更新失败: ' + e.message)
  } finally {
    row._saving = false
  }
}

// 追踪库
const tracedList = ref([])
const tracedLoading = ref(false)
const tracedSaving = ref(false)
const addTracedDialogVisible = ref(false)
const addTracedForm = ref({ target: '', port: '', note: '' })

async function loadTraced() {
  tracedLoading.value = true
  try {
    const res = await fetchTracedList()
    tracedList.value = Array.isArray(res) ? res : (res.items || [])
  } catch (e) {
    ElMessage.error('加载追踪列表失败: ' + e.message)
  } finally {
    tracedLoading.value = false
  }
}

function beforeUploadTraced(file) {
  const isExcel = file.name.endsWith('.xlsx') || file.name.endsWith('.xls')
  if (!isExcel) {
    ElMessage.error('只支持 .xlsx / .xls 文件')
    return false
  }
  return true
}

async function handleUploadTraced({ file }) {
  try {
    await importTraced(file)
    ElMessage.success('追踪库导入成功')
    loadTraced()
  } catch (e) {
    ElMessage.error('追踪库导入失败: ' + e.message)
  }
}

async function confirmAddTraced() {
  if (!addTracedForm.value.target) {
    ElMessage.warning('目标不能为空')
    return
  }
  tracedSaving.value = true
  try {
    await createTraced(addTracedForm.value)
    ElMessage.success('添加成功')
    addTracedDialogVisible.value = false
    addTracedForm.value = { target: '', port: '', note: '' }
    loadTraced()
  } catch (e) {
    ElMessage.error('添加失败: ' + e.message)
  } finally {
    tracedSaving.value = false
  }
}

async function handleDeleteTraced(row) {
  try {
    await ElMessageBox.confirm(`确定删除追踪目标「${row.target}」？`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteTraced(row.id)
    ElMessage.success('删除成功')
    loadTraced()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败: ' + e.message)
    }
  }
}

// ====== Tab 3: 系统设置 ======

const configForm = ref({
  trace_ttl_days: 90,
  default_hide_traced: true,
  default_hide_closed: true,
  badges: [],
})
const configSaving = ref(false)

const badgeOptions = [
  { id: 'apt_dict', label: 'APT词典' },
  { id: 'advanced_crime', label: '高级黑灰产' },
  { id: 'noise_family', label: '噪声家族' },
  { id: 'multi_vendor', label: '多厂商' },
  { id: 'cross_day', label: '跨天持续' },
  { id: 'lateral', label: '横向扩散' },
  { id: 'expired_revive', label: '追踪过期' },
  { id: 'high_tier', label: '高级别' },
  { id: 'scan_noise', label: '疑似扫描' },
]

async function loadConfig() {
  try {
    const cfg = await fetchConfig()
    configForm.value.trace_ttl_days = cfg.trace_ttl_days || 90
    configForm.value.default_hide_traced = !!cfg.default_hide_traced
    configForm.value.default_hide_closed = !!cfg.default_hide_closed
    configForm.value.badges = cfg.badges || badgeOptions.map(b => b.id)
  } catch {
    // 配置接口不可用时使用默认值
  }
}

async function handleSaveConfig() {
  configSaving.value = true
  try {
    await saveConfig(configForm.value)
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  } finally {
    configSaving.value = false
  }
}

// 表格列设置
const { columns, toggleColumn } = useColumnConfig()
const columnSettings = computed(() => columns.value.map(c => ({ ...c })))
const savedColumnSnapshot = ref(JSON.stringify(columns.value.map(c => ({ key: c.key, width: c.width, visible: c.visible }))))
const hasPendingColumnChanges = computed(() => {
  const current = JSON.stringify(columns.value.map(c => ({ key: c.key, width: c.width, visible: c.visible })))
  return current !== savedColumnSnapshot.value
})

function toggleColumnSetting(key) {
  toggleColumn(key)
}

function moveColumn(idx, direction) {
  const cols = columns.value
  const newIdx = idx + direction
  if (newIdx < 0 || newIdx >= cols.length) return
  const temp = cols[idx]
  cols[idx] = cols[newIdx]
  cols[newIdx] = temp
  columns.value = [...cols]
}

function handleSaveColumnSettings() {
  saveColumnOrder(columns.value)
  savedColumnSnapshot.value = JSON.stringify(columns.value.map(c => ({ key: c.key, width: c.width, visible: c.visible })))
  ElMessage.success('列设置已保存')
}

// 词典
const dicts = ref(null)
const dictsLoading = ref(false)

async function loadDicts() {
  dictsLoading.value = true
  try {
    dicts.value = await fetchDicts()
  } catch (e) {
    ElMessage.error('加载词典失败: ' + e.message)
  } finally {
    dictsLoading.value = false
  }
}

function dictDisplayName(name) {
  const map = {
    apt_org_dict: 'APT 组织词典',
    advanced_crime: '高级黑产词典',
    noise_family: '噪声家族词典',
  }
  return map[name] || name
}

// ====== Tab 4: 系统信息 ======
const versionInfo = ref({
  version: 'unknown',
  git_commit: null,
  git_remote_url: null,
  update_available: false,
  local_ahead: false,
  is_git_repo: false,
})
const versionChecking = ref(false)
const changelog = ref('')
const changelogLoading = ref(false)

async function loadVersion() {
  try {
    versionInfo.value = await fetchVersion()
  } catch {
    // 静默失败
  }
}

async function loadChangelog() {
  changelogLoading.value = true
  try {
    const res = await fetch('/CHANGELOG.md')
    if (res.ok) {
      changelog.value = await res.text()
    } else {
      changelog.value = '# 暂无变更日志\n\n当前版本无变更记录。'
    }
  } catch {
    changelog.value = '加载变更日志失败。'
  } finally {
    changelogLoading.value = false
  }
}

async function checkUpdate() {
  versionChecking.value = true
  try {
    versionInfo.value = await fetchVersion()
    if (versionInfo.value.update_available) {
      ElMessage.info('检测到新版本，请运行 update.bat 更新代码。')
    } else if (!versionInfo.value.is_git_repo) {
      ElMessage.info('当前未使用 Git 管理，无法检查更新。')
    } else {
      ElMessage.success('已是最新版本。')
    }
  } catch (e) {
    ElMessage.error('检查更新失败: ' + e.message)
  } finally {
    versionChecking.value = false
  }
}

function goToUpdate() {
  ElMessage.info('请在终端中运行 update.bat 更新代码，然后启动平台（数据库将自动迁移）。')
}

function openBackupsDir() {
  ElMessage.info('备份目录位于项目根目录的 backups/ 文件夹中。')
}

// 初始化
onMounted(() => {
  loadImports()
  loadBatches()
  loadTraced()
  loadConfig()
  loadDicts()
  loadVersion()
  loadChangelog()
  loadAllTags()
})

onBeforeUnmount(() => {
  stopImportPolling()
})
</script>

<style scoped>
.settings-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.page-title {
  margin: 0 0 12px 0;
  color: var(--text-primary);
  font-size: 18px;
}

.settings-tabs {
  flex: 1;
}

.settings-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}

.settings-tabs :deep(.el-tabs__content) {
  height: calc(100% - 55px);
  overflow-y: auto;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card {
  background-color: var(--bg-secondary);
  border-color: var(--border-color);
  box-shadow: var(--shadow-card);
}

.section-card :deep(.el-card__header) {
  background-color: var(--card-header-bg);
  border-bottom: 1px solid var(--border-color);
  padding: 10px 16px;
}

.section-card :deep(.el-card__body) {
  padding: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.upload-area {
  text-align: center;
  padding: 16px;
}

.upload-icon {
  font-size: 36px;
  color: var(--accent);
  margin-bottom: 12px;
}

.upload-area p {
  color: var(--upload-text);
  margin: 4px 0;
}

.upload-hint {
  font-size: 12px;
  color: var(--upload-hint);
}

.mb-8 {
  margin-bottom: 8px;
}

.mt-12 {
  margin-top: 12px;
}

.upload-progress {
  margin-top: 12px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border-color);
}
.upload-progress__label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.upload-progress__pct {
  font-weight: 600;
  color: var(--accent);
}

.processing-status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 13px;
  flex-wrap: wrap;
}

.processing-detail {
  font-size: 12px;
  color: var(--text-muted);
}

.processing-progress {
  width: 100%;
  margin-top: 4px;
}

/* 不确定进度的进度条：用条纹动画表示「正在处理」 */
.processing-progress--unknown :deep(.el-progress-bar__inner) {
  background: linear-gradient(90deg, var(--primary) 25%, var(--accent) 25%, var(--accent) 50%, var(--primary) 50%, var(--primary) 75%, var(--accent) 75%);
  background-size: 200% 100%;
  animation: processing-stripe 1.5s linear infinite;
  min-width: 100% !important;
}

@keyframes processing-stripe {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.processing-tag {
  margin-left: auto;
}

.blink-tag {
  animation: blink 1.2s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.queue-pos {
  display: inline-block;
  min-width: 20px;
  padding: 2px 6px;
  background: var(--bg-tertiary, #1a1a3a);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, #9090a8);
}

.import-result {
  margin-top: 12px;
}

.batch-device-input {
  margin-bottom: 10px;
}

.batch-tag-actions {
  display: flex;
  gap: 8px;
}

.batch-tag-select {
  width: 100%;
}

.traced-upload-row {
  margin-bottom: 8px;
}

.config-form {
  max-width: 600px;
}

.dicts-display {
  max-height: 500px;
  overflow-y: auto;
}

.dict-section {
  margin-bottom: 16px;
}

.dict-name {
  color: var(--text-primary);
  margin: 0 0 6px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 4px;
}

.dict-content {
  background: var(--bg-primary);
  color: var(--text-secondary);
  padding: 10px;
  border-radius: 4px;
  font-size: 12px;
  max-height: 200px;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  border: 1px solid var(--border-color);
}

.batch-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.batch-device-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.batch-device-list {
  font-family: monospace;
  font-size: 12px;
}

/* Import detail dialog */
.import-stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.stat-card {
  flex: 1;
  text-align: center;
  padding: 12px 8px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  position: relative;
}

.stat-card.stat-total { border-left: 3px solid #909399; }
.stat-card.stat-success { border-left: 3px solid #67C23A; }
.stat-card.stat-skipped { border-left: 3px solid #909399; }
.stat-card.stat-raw { border-left: 3px solid #E6A23C; }
.stat-card.stat-failed { border-left: 3px solid #F56C6C; }

.stat-num {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.stat-label {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.stat-help {
  font-size: 12px;
  color: var(--text-muted);
  cursor: help;
}

.import-meta {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.detail-section {
  margin-top: 16px;
}

.detail-section-title {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.detail-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.detail-section-header .detail-section-title {
  margin: 0;
}

.detail-section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.error-text {
  color: #F56C6C;
  font-size: 12px;
}

.no-error-text {
  color: var(--text-muted);
}

.detail-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.raw-json-popover {
  max-height: 400px;
  overflow: auto;
  font-size: 11px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 8px;
  border-radius: 4px;
}

/* System info tab */
.commit-hash {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.remote-url {
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
}

.text-muted {
  color: var(--text-muted);
}

.system-actions {
  margin-top: 16px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.update-hint {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}

.changelog-content {
  max-height: 500px;
  overflow-y: auto;
}

.changelog-content pre {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.data-management {
  display: flex;
  align-items: center;
  gap: 12px;
}

.data-hint {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
