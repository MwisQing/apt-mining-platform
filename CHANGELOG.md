# Changelog

## v3.3.6 - 2026-05-18

- 修复：上传 Excel 卡死平台 — 根因定位与 3 项修复
  - **根因1**：SQLite 单连接（StaticPool）— 导入队列 worker 持有唯一连接，其他请求全部阻塞
  - **根因2**：Excel 全量加载内存爆炸 — pandas 将 10万行 × 24列全部加载为 DataFrame + dict + JSON 字符串，峰值 500MB-1GB
  - **根因3**：导入后自动快照重建 — 首次构建 ~110s，大量 DB 读写加重平台负载
- 修复：`db.py` — SQLite 连接池改为 `QueuePool(pool_size=5, max_overflow=3)`，多连接并发，导入不再独占
- 修复：`imports.py` — `_process_excel` 改用 openpyxl `read_only` 模式逐行流式读取，每 500 行 batch commit，内存峰值降至 ~50MB
- 修复：`imports.py` — 导入完成后不再自动触发 `rebuild_candidate_snapshots_async()`，快照按需构建
- 优化：`requirements.txt` — 移除重复的 `openpyxl` 条目

## v3.2.4 - 2026-05-13

- 新增：`start.py --daemon` 后台运行模式（Linux），脱离终端会话，SSH 断开不中断；日志输出到 `logs/backend.log`，PID 写入 `backend.pid`
- 新增：`stop.py` 优先从 PID 文件停止后台进程，回退到端口扫描
- 修复：Linux 默认绑定 `0.0.0.0`（Windows 仍为 `127.0.0.1`），解决外部无法访问
- 修复：`upgrade.py` `check_git()` 使用 `command -v git`（Linux）替代 `where git`（Windows）
- 修复：`upgrade.py` `install_backend_deps()` venv 路径跨平台兼容
- 修复：`pack_release.py` vite build 命令移除 `--registry` 参数（vite 不识别）
- 新增：`upgrade.py` 更新后自动 `chmod +x` 所有 Python 和 .sh 运维脚本（Linux/macOS），包含 `start.sh`/`stop.sh`/`install.sh`
- 修复：`upgrade.py` `build_frontend()` 检测到已有 `frontend/dist/index.html` 时跳过 `npm install + build`（无外网服务器避免卡死）
- 修复：`install.py` 跳过已存在的 `frontend/dist` 构建产物

## v3.2.0 - 2026-05-12

- 新增：候选快照表系统（alert_candidate_snapshots + badge/tag 子表，active version 切换模型）
- 新增：后端全量缓存分桶（按基础筛选条件分桶，切换日期零 SQL）
- 新增：heat map 单次聚合查询（6次独立 SQL 合并为 1 次）
- 新增：expired_revive badge 预加载 traced_targets 索引（消除 N+1）
- 新增：快照构建中状态提示（Workbench 页顶部 el-alert）
- 新增：正式/测试实例配置化（APT_SERVER_HOST/PORT/DB_PATH 环境变量）
- 新增：start.py/start_test.py/stop.py/stop_test.py 替代旧 bat 脚本
- 新增：研判工作台「告警次数」列
- 修复：大 IN (...) 查询分批处理（规避 SQLite too many SQL variables）
- 修复：研判工作台表格行高异常与数据偏移（移除优先级列 fixed 属性）
- 修复：priority 列排序/显隐/列宽配置
- 优化：首次加载 SQL 从 14 次降至 3 次
- 优化：upgrade.py ZIP 升级模式目录逐文件合并（保留本地额外文件）
- 优化：标签颜色管理（PATCH /api/tags/tags/{tag_id} + 前端 Settings 页）

## v3.1.4 - 2026-05-11

- 修复：研判工作台排序功能（SortButton 改为 h() render 函数）
- 修复：表头筛选全表范围（page_size=99999 全量拉取 + 前端过滤分页）
- 修复：关键字搜索误命中（移除 intel_tags/vendors LIKE 匹配）
- 修复：候选列表取消规则过滤（展示全部告警按评分排序）
- 新增：列配置文件化（columns.json 默认值 + localStorage 覆盖 + 恢复默认）
- 新增：设备ID列默认宽度 130→160px
- 优化：push_release.py 适配 GitHub 纯净包场景（自动 init + 自动配置远程仓库）

## v3.1.3 - 2026-05-09

- 新增：测试端口隔离（start-test.bat/stop-test.bat，端口 9099）
- 新增：研判工作台排除标签筛选（exclude_device_tags）
- 新增：侧边栏导航改为 router-link 支持鼠标中键新标签页
- 修复：导入缺失 analysis_status/is_focused 字段
- 修复：事件管理自动保存改为手动提交
- 修复：IOC 提取域名子域名误杀

## v3.1.2 - 2026-05-09

- 新增：已导入数据元数据修复接口（POST /api/imports/{id}/repair-metadata）
- 修复：设备标签不显示 bug（tags.py 未清空候选缓存）
- 修复：标签批次软删除 + 一键恢复

## v3.1.1 - 2026-05-09

- 新增：混合模式一键升级系统（upgrade.py / pack_release.py / push_release.py）
- 新增：Alembic 数据库版本管理与基线迁移
- 新增：WebUI 系统信息 Tab（版本号/变更日志/更新检查）
- 新增：VERSION / CHANGELOG.md 版本管理

## v3.1 - 2026-05-08

- 新增：全量缓存候选查询，排序/翻页零 DB 查询
- 新增：Excel 风格表头下拉筛选（7列）
- 新增：上传进度条实时显示
- 新增：平台版本更新与数据迁移系统
- 修复：resize/sort 冲突
- 修复：全量缓存 SQLite 表达式树溢出
