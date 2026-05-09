# APT Mining Workbench — AI 协作上下文

> **本文件是 AI 助手的上下文入口。每次新对话开始时，AI 必须先读取本文件。**
> **每完成一个阶段后，AI 必须更新底部的"进度记录"部分。**

---

## 项目概述

APT 挖掘工作台：安全分析师从海量网络告警中挖掘 APT 事件的单机离线平台。

**技术栈：** FastAPI + SQLite（后端） / Vue 3 + Vite + Element Plus（前端）
**运行方式：** 本地启动，浏览器访问 `http://127.0.0.1:8088`

---

## 用户工作流

```
1. 收到告警 Excel（10w 条）→ 上传导入平台
2. 导入设备标签 TXT（01排查成功/02重点设备/03不好查）→ 批量打标
3. 打开研判工作台 → 看候选结果（已自动筛apt/远控、评分、排序）
4. 逐条研判：
   - 有价值 → 创建事件（关联IOC+端口），事件按IOC匹配自动命中
   - 已知的 → 标记追踪过
   - 设备排查完 → 更新设备标签
5. 下次导入新数据，之前的标签和追踪自动生效
```

> **事件匹配规则（阶段28起）：** 事件仅通过 IOC+端口 匹配告警行，不再通过设备ID匹配。设备标签仍按设备ID独立展示。

---

## 项目目录结构

```
apt-mining-platform/
├── backend/                    # FastAPI 后端（已完成，基本不需要改）
│   ├── main.py                 # 入口，挂载所有路由
│   ├── api/
│   │   ├── alerts.py           # 告警列表 + 候选接口
│   │   ├── imports.py          # Excel 导入
│   │   ├── events.py           # 事件 CRUD
│   │   ├── tags.py             # 设备标签 + TXT 批量导入
│   │   ├── traced.py           # IOC 追踪
│   │   ├── devices.py          # 设备列表
│   │   ├── config.py           # 配置读写
│   │   └── persistence.py      # 跨天持续外联查询
│   ├── models/                 # SQLAlchemy 模型
│   ├── services/
│   │   ├── __init__.py         # Badge 计算引擎
│   │   └── alert_workbench.py  # 候选规则、评分、内容哈希
│   └── utils/
│       ├── __init__.py         # 配置/词典加载
│       └── db.py               # SQLite engine + session
├── frontend/                   # 前端（需要重建）
│   ├── src/                    # Vue 3 源码（待创建）
│   └── dist/                   # 旧打包产物（重建后替换）
├── config/
│   ├── config.yaml             # 主配置
│   ├── apt_org_dict.yaml       # APT 组织词典
│   ├── advanced_crime.yaml     # 高级黑产词典
│   └── noise_family.yaml       # 噪声家族词典
├── uploads/                    # 上传文件暂存
├── CLAUDE.md                   # ← 本文件
├── start.bat
├── install.bat
└── requirements.txt
```

---

## 后端 API 完整清单

### 告警与候选

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/alerts` | 告警列表（分页、筛选、badge） |
| GET | `/api/alerts/options` | 动态筛选选项（威胁类型、标签等） |
| GET | `/api/alerts/export.csv` | 导出告警 CSV |
| GET | `/api/alert-candidates` | **候选结果**（核心接口，含评分、热度、追踪状态） |

#### `/api/alert-candidates` 参数
```
date_start, date_end       日期范围
target_type                目标类型
target_kind                all|ip|domain|other
device_tags                设备标签ID（逗号分隔）
threat_types               威胁类型（逗号分隔）
threat_levels              威胁等级（逗号分隔）
apt_tiers                  APT分级（逗号分隔）
hide_traced                隐藏已追踪（默认读配置）
hide_closed                隐藏已关闭事件（默认读配置）
keyword                    关键词搜索
alert_count_max            告警次数上限
badges_filter              徽章筛选
page, page_size            分页
```

#### `/api/alert-candidates` 返回结构
```json
{
  "items": [
    {
      "id": 1,
      "device_id": "xxx",
      "source_ip": "10.x.x.x",
      "target": "evil.com",
      "port": "443",
      "threat_type": "apt",
      "threat_level": "high",
      "std_apt_org": "oceanlotus",
      "apt_org": "海莲花",
      "apt_org_tier": "一级",
      "vendors": "厂商A,厂商B",
      "first_alert_time": "2026-04-29 09:00:00",
      "last_alert_time": "2026-04-29 18:00:00",
      "alert_count": 5,
      "badges": [{"name": "apt_dict", "label": "APT词典", "color": "red"}],
      "candidate_rule_ids": ["threat_type_apt"],
      "candidate_reasons": ["威胁类型命中APT", "已映射标准APT组织"],
      "candidate_score": 85,
      "candidate_priority": {"id": "p2", "label": "中优先", "rank": 2},
      "target_kind": "domain",
      "heat": {
        "target_alert_count": 12,
        "target_device_count": 3,
        "source_ip_alert_count": 8,
        "device_alert_count": 5
      },
      "device_tags": [{"id": 1, "name": "重点设备", "color": "#F56C6C"}],
      "trace_status": null,
      "event_status": null
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 100,
  "meta": {
    "platform_scope": "...",
    "candidate_scope": "...",
    "differences_from_script": "..."
  }
}
```

### 事件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/events` | 事件列表（可选 ?status=active） |
| POST | `/api/events` | 创建事件 `{event_name, color, note, devices:[], iocs:[{target,port}]}`（事件按IOC匹配告警，devices仅作记录） |
| GET | `/api/events/{id}` | 事件详情（含 devices, iocs, followups） |
| PATCH | `/api/events/{id}` | 更新事件 `{event_name, color, note, status}` |
| DELETE | `/api/events/{id}` | 删除事件 |
| POST | `/api/events/{id}/followups` | 添加跟进 `{action_type, note}` |
| POST | `/api/events/{id}/devices` | 关联设备 `{devices:[]}` |
| POST | `/api/events/{id}/iocs` | 关联IOC `{iocs:[{target,port}]}` |
| DELETE | `/api/events/{id}/devices/{device_id}` | 移除设备关联 |
| DELETE | `/api/events/{id}/iocs?target=x&port=y` | 移除IOC关联 |

### 标签

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tags` | 标签列表 |
| GET | `/api/tags/batches` | 标签批次列表 |
| POST | `/api/tags/batches` | 创建批次 `{batch_name, tag_name, color, devices:[], note}` |
| POST | `/api/tags/batches/import-text-files` | **上传TXT批量打标**（multipart files） |
| DELETE | `/api/tags/batches/{id}` | 删除批次（连带标签和关联） |
| GET | `/api/tags/devices/{device_id}/tags` | 设备的标签 |
| POST | `/api/tags/devices/tags` | 给设备打标 `{device_id, tag_name, color}` |
| DELETE | `/api/tags/devices/{device_id}/tags/{tag_id}` | 移除设备标签 |

### 追踪

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/traced` | 追踪列表（?keyword=） |
| POST | `/api/traced` | 添加追踪 `{target, port, note}` 或数组 |
| POST | `/api/traced/import` | **上传追踪库Excel**（multipart file） |
| PATCH | `/api/traced/{id}` | 更新追踪 |
| DELETE | `/api/traced/{id}` | 删除追踪 |

### 导入

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/imports` | **上传Excel告警**（multipart files，后台异步处理） |
| GET | `/api/imports` | 导入历史列表 |
| GET | `/api/imports/{id}` | 导入详情 |
| GET | `/api/imports/{id}/sheets` | Sheet列表 |
| GET | `/api/imports/{id}/rows` | 行明细（?sheet_id=&status=&page=） |
| GET | `/api/imports/{id}/failures.csv` | 下载失败行CSV |
| DELETE | `/api/imports/{id}` | 删除导入（含关联告警） |

### 设备

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/devices` | 设备列表（?keyword=&tags=&page=&page_size=） |

### 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 读配置 |
| POST | `/api/config` | 保存配置 `{trace_ttl_days, default_hide_traced, default_hide_closed, badges:[]}` |
| POST | `/api/config/reload` | 重载词典 |
| GET | `/api/config/dicts` | 获取词典内容 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/persistence` | 跨天持续外联（?min_days=&since=&limit=） |

---

## 前端开发约定

- **框架：** Vue 3 (Composition API) + Vite + Element Plus
- **语言：** JavaScript（不用 TypeScript）
- **样式：** Element Plus 默认主题 + 少量自定义 CSS，暗色调配色
- **状态管理：** 不需要 Vuex/Pinia，用组件本地状态 + props/emit
- **HTTP 请求：** axios，统一封装在 `src/api/` 目录
- **路由：** Vue Router，4 个主页面
- **图标：** Element Plus 内置图标
- **构建产物：** `frontend/dist/`，后端 FastAPI 直接 mount 静态文件

### 页面规划

| 路由 | 页面 | 对接 API | 优先级 |
|------|------|----------|--------|
| `/` | 研判工作台 | `/api/alert-candidates` | P0 |
| `/alerts` | 原始告警列表 | `/api/alerts` | P2 |
| `/events` | 事件管理 | `/api/events` | P1 |
| `/settings` | 导入与设置 | `/api/imports` + `/api/config` + `/api/tags` + `/api/traced` | P1 |

---

## 候选评分规则（当前版本）

| 规则 | 字段 | 关键词 | 基础分 |
|------|------|--------|--------|
| 威胁类型命中APT | threat_type | apt | 34 |
| 威胁类型命中远控 | threat_type | 远控, remote | 30 |
| 已映射标准APT组织 | std_apt_org | (非空) | 26 |
| 原始APT组织非空 | apt_org | (非空) | 22 |
| 情报标签命中 | intel_tags | apt, c2, 远控, remote | 18 |

额外加分：威胁等级、APT分级、目标热度、设备热度、多厂商、事件关联、设备标签
减分：已追踪（活跃-12，过期-4）

优先级：≥110 高优先 / ≥75 中优先 / 其他 观察

---

## Badge 类型

| 名称 | 标签 | 颜色 | 触发条件 |
|------|------|------|----------|
| apt_dict | APT词典 | red | std_apt_org 命中 APT 词典 |
| advanced_crime | 高级黑灰产 | purple | apt_org 命中高级黑产词典 |
| noise_family | 噪声家族 | gray | threat_type 命中噪声词典 |
| multi_vendor | 多厂商 | yellow | 厂商数 ≥ 3 |
| cross_day | 跨天持续 | green | 同源IP+目标跨天出现 |
| lateral | 横向扩散 | blue | 同源IP对 ≥3 个目标 |
| expired_revive | 追踪过期 | orange | 追踪超过TTL天数 |
| high_tier | 高级别 | gold | APT分级=一级 |
| scan_noise | 疑似扫描 | lightgray | 告警次数 > 1000 |

---

## 数据库表（SQLite）

核心表：`alerts`, `mined_events`, `mined_event_devices`, `mined_event_iocs`, `event_followups`, `tags`, `tag_batches`, `device_tags`, `traced_targets`, `imports`, `import_sheets`, `import_rows`, `audit_log`

---

## 开发注意事项

1. 后端已经可用，前端重建时直接对接 API，不要改后端（除非 API 缺字段）
2. 前端代理配置：开发时 Vite proxy → `http://127.0.0.1:8088`
3. 生产构建后 dist 放在 `frontend/dist/`，后端自动 mount
4. 所有时间字段都是字符串格式 `"YYYY-MM-DD HH:MM:SS"`
5. 后端 CORS 已全开放（`allow_origins=["*"]`）
6. 导入是异步的：POST 后返回 job，需轮询 GET `/api/imports/{id}` 查状态
7. **前端已重建完成**（阶段0~5），所有4个页面已实现。后续迭代直接修改 `frontend/src/` 下的 Vue 组件，开发时 `npm run dev`，生产 `npm run build`

---

## 进度记录

> **AI 每完成一个阶段，必须在此处更新。格式：日期 + 阶段编号 + 完成内容摘要。**

| 日期 | 阶段 | 内容 |
|------|------|------|
| 2026-04-30 | 阶段0 | 前端项目初始化完成：Vite+Vue3项目搭建，安装vue-router/axios/element-plus，vite代理配置，App.vue侧边栏暗色布局，4个路由+空壳页面，全局暗色调样式，axios封装+响应拦截器 |
| 2026-04-30 | 阶段1 | 研判工作台页面实现：顶部筛选栏（日期范围、目标类型切换、隐藏已追踪/已关闭开关、关键词搜索），主体表格14列（优先级/分数/设备ID/设备标签/外联目标/端口/威胁类型/APT组织/目标热度/追踪状态/事件状态/命中原因/徽章/操作），行高亮（高优先红/中优先橙），分页组件，标记追踪对话框（POST /api/traced），创建事件对话框（POST /api/events），API模块封装（candidates.js/traced.js/events.js/config.js），页面初始化自动加载配置和候选数据 |
| 2026-04-30 | 阶段2 | 导入与设置页面实现：三个Tab（数据导入/标签管理/系统设置）。Tab1：拖拽上传Excel（POST /api/imports），3秒轮询处理状态，导入历史表格（状态Tag闪烁），导入详情Dialog（Sheet列表），删除导入。Tab2：TXT批量导入打标（POST /api/tags/batches/import-text-files），标签批次记录表格+撤销，追踪库Excel导入+手动添加+删除。Tab3：配置表单（TTL天数/隐藏开关/Badge多选）保存，词典只读展示。API模块补充（imports.js/tags.js完整封装，traced.js补充import/update/delete，config.js补充fetchDicts/reloadDicts） |
| 2026-04-30 | 阶段3 | 事件管理页面实现：左右分栏布局（左侧350px列表+右侧详情）。左侧：事件卡片列表（左侧色条/名称/状态Tag/挖掘时间），状态筛选（全部/活跃/已关闭），创建事件按钮。右侧：事件详情头部（名称/颜色点/状态切换开关/编辑/删除），关联设备区域（Tag展示+删除+添加Dialog），关联IOC区域（target:port格式Tag+删除+添加Dialog），跟进记录时间线（type+note+底部快捷输入），备注可编辑（失焦自动保存）。事件CRUD对话框（创建/编辑复用表单），删除二次确认。API模块events.js扩充10个方法（fetchEvents/fetchEvent/createEvent/updateEvent/deleteEvent/addFollowup/addDevices/addIocs/removeDevice/removeIoc） |
| 2026-04-30 | 阶段4 | 原始告警列表页面实现：顶部筛选栏（日期范围、目标类型下拉、威胁类型/等级多选、设备标签多选、关键词搜索、隐藏已追踪开关、导出CSV按钮），主体表格16列（设备ID/源IP/外联目标/端口/威胁类型/威胁等级/标准APT组织/APT组织/厂商/告警次数/首次告警时间/最近告警时间/徽章/设备标签/追踪状态/事件状态），分页50/100/200/500，筛选选项动态获取GET /api/alerts/options，导出CSV通过GET /api/alerts/export.csv带当前筛选参数。API模块alerts.js封装（fetchAlerts/fetchAlertOptions/exportAlertsCsv） |
| 2026-04-30 | 阶段5 | 集成联调与生产构建：解压后端runtime包，创建venv安装依赖，启动后端验证所有API（/api/health /api/alerts /api/alerts/options /api/alert-candidates /api/events /api/traced /api/tags /api/imports /api/config）正常返回空数据不报错，启动前端dev服务器验证proxy代理正常，执行npm run build生成frontend/dist/产物，验证后端正确mount静态文件（index.html + JS/CSS assets均返回200）。前端已重建完成，后续迭代可直接修改 frontend/src/ 下的 Vue 组件 |
| 2026-04-30 | 阶段7 | 三主题切换系统：暗色/VSCode浅色/VS2026蓝色。CSS变量系统（40+变量）统一管理全部颜色，`data-theme`属性切换。侧边栏底部3按钮切换器，localStorage持久化主题选择。各组件hardcoded颜色全面替换为var(--xxx)引用。Element Plus组件（表格/对话框/卡片/输入框/按钮）通过[data-theme]选择器跟随主题。重启后自动读取保存的主题。 |
| 2026-04-30 | 阶段6 | 全链路修复与暗色主题上线：(1)配置修复：config.yaml db路径从tmp_feature_regression.db改为data/workbench.db，start.bat端口从9099统一为8088，创建data目录；(2)前端Bug修复：EventManager.vue设备列表dev.device_id→dev（后端返回字符串数组），Workbench.vue追踪状态从布尔判断改为三态（active/expired/none），事件列从event_status改为event.event_name展示带颜色标签，AlertList.vue同样修复trace_status和event列，Settings.vue导入表格字段名file_name→source_file等与后端对齐，el-button-group改用独立按钮+click替代v-model；(3)导出修复：alerts.js exportAlertsCsv→exportAlerts改为POST /api/alerts/export返回xlsx blob下载，handleExportCsv改为async；(4)暗色主题：global.css全局暗背景#0a0a1a，App.vue暗色侧边栏#0d0d24带品牌标识，4个页面全部暗色化（面板#12122a、表头#1a1a3a、边框#2a2a4a、文字#d0d0d0/#9090a8）；(5)演示数据：生成200条含APT/远控/扫描/流量异常的模拟告警Excel，导入验证评分候选182条P1多条目，创建3个TXT标签文件上传打标，创建测试事件+追踪记录，全链路验证通过 |
| 2026-04-30 | 阶段8 | 8项修复与优化：(1)/settings刷新404→添加SPA fallback路由`/{full_path:path}`，API路由优先匹配，非API路径fallback到index.html；(2)表头列宽拖拽线→resize-handle改为always visible的2px竖线(border-right)，右侧6px可拖拽区域，hover高亮；(3)demo_alerts.xlsx→用真实Excel表头生成100000条数据，含APT/远控/扫描多种威胁类型和分级；(4)大数据量前端卡顿→降低默认page_size从100到50，添加row-key提高Vue虚拟DOM效率，增加6个数据库索引(first_alert_time/device_id/target/source_ip/threat_type/std_apt_org)，导入时启用PRAGMA优化(temp_store=MEMORY,mmap_size)；(5)排序无响应→将@mousedown.stop从resizable-header div移到resize-handle span，修复mousedown拦截sort-click的冲突；(6)研判状态/重点关注→改为纯展示列，移除el-select和star-toggle交互控件，仅通过列选择器控制显隐；(7)IOC自动提取→增强extract_iocs_from_text支持redacted IP/MD5/network:前缀/path:前缀/URL，返回全部类型(IP/域名/MD5/路径/URL)到iocs列表；(8)平台长期运行卡顿→WAL checkpoint每30分钟TRUNCATE(每5分钟PASSIVE)，启用wal_autocheckpoint=1000限制WAL大小，定期gc.collect()清理内存，导入后释放hash_rows游标引用 |
| 2026-05-01 | 阶段10 | 真实数据性能+告警页修复：(1)content_hash去除时间字段；(2)/api/alerts/options补充target_types/threat_levels；(3)五层模式生成10万条仿真数据；(4)vite.config.js proxy修正9099→8088；(5)后端sort_by/sort_order SQLite分页排序；(6)前端shallowRef+requestSeq防抖 |
| 2026-05-01 | 阶段11 | 排序性能+IOC增强+事件创建优化：(1)SQL级候选评分(SQL_BASE_CANDIDATE_SCORE CASE WHEN聚合)，所有计算字段均可SQL分页排序(加分/热度/追踪状态)，不再走全量Python装饰慢路径；(2)IOC提取支持中文冒号(：)端口，新增设备ID自动提取(LAPTOP/SRV/PC/WIN等前缀)，IP+端口联动提取；(3)Workbench事件对话框重设计：备注10行、粘贴自动解析设备+IOC、15种预设颜色+自定义、批量添加/清空设备/IOC；(4)EventManager批量添加设备/IOC对话框；(5)创建事件自动给设备打标签 |
| 2026-05-02 | 阶段14 | 重复设备标签修复+批量打标记录：(1)后端`_device_tag_map_for_rows`增加名称去重（同名字段只显示一个tag），启动时`_dedupe_tags`自动合并历史重复标签记录，优先保留永久标签；(2)`POST /api/tags/devices/batch`新增`record_batch`参数（默认true），批量打标时自动创建tag_batches记录，操作可见于标签批次记录并支持一键撤销；(3)`list_batches`返回`tag_name`和`color`字段修复前端批次表格显示；(4)事件自动打标保持`is_permanent=1`查找、单设备打标移除`is_permanent`过滤防止重复创建同名标签 |
| 2026-05-02 | 阶段15 | 候选列表去重：(1)候选查询 `/api/alert-candidates` 增加SQL级去重，按 `(device_id, target, port)` 分区，`ROW_NUMBER()` 窗口函数保留每分区最高`alert_count`+最新时间的行；(2)COUNT查询同步更新为 `GROUP BY` 后计数；(3)`_make_items` 中 `pop("_rn")` 清理内部字段不返回前端。效果：32533条候选→25085条唯一连接，同设备同目标同端口只显示一条 |
| 2026-05-02 | 阶段16 | 标签批次增强+重复标签显示bug修复：(1)新增`GET /api/tags/batches/{id}`批次详情(含设备列表)、`DELETE /api/tags/batches/{id}/devices`部分删除设备、`POST /api/tags/batches/{id}/restore`一键恢复打标；(2)前端Settings.vue新增详情Dialog(设备列表+部分删除)、一键恢复按钮、删除按钮替代旧撤销按钮；(3)修复SRV-HZ-618设备标签显示两次bug：根因为标签名末尾含`\t`制表符导致`_dedupe_tags`未合并且`_device_tag_map_for_rows`名称去重失效；(4)所有标签创建点(tags.py events.py)增加strip()去除首尾空白；(5)`_dedupe_tags`改为`RTRIM`清理历史数据+逐行UPDATE避免`UPDATE OR IGNORE`整条失败；(6)`_device_tag_map_for_rows`名称去重改为strip()后比较 |
| 2026-05-02 | 阶段17 | 标签批次软删除：(1)tag_batches表新增status字段(active/deleted)，db.py _ensure_runtime_schema自动迁移；(2)DELETE /api/tags/batches/{id}改为软删除(UPDATE status='deleted')，保留标签和设备关联；(3)list_batches返回status字段；(4)restore_batch恢复时重置status='active'；(5)前端批次表格新增「状态」列显示活跃/已删除Tag；(6)已删除批次禁用删除按钮；(7)批次详情Dialog显示状态；(8)TagBatch模型新增status字段 |
| 2026-05-01 | 阶段13 | IOC备注替代追踪+新页面+多项修复：(1)hide_closed IOC端口通配匹配修复+config字段名修正；(2)研判工作台「追踪」列替换为「IOC备注」列显示trace note内容；(3)移除工作台「操作」列（标记追踪/创建事件按钮）；(4)新建IOC备注管理页面(/ioc-notes)支持表格展示、单条删除、批量删除、添加编辑；(5)事件关联设备/IOC保存加防并发guard；(6)搜索框自动trim空格；(7)Element Plus全局中文locale+日期选择器中文格式；(8)EventManager描述textarea加长(14行)、设备/IOCtextarea缩短(3行)并加max-width | 2026-05-01 | 阶段12 | 性能修复+新字段+事件识别重构：(1)候选查询默认按candidate_score DESC SQL排序，避免无sort时走全量Python装饰慢路径导致的长时间loading；(2)新增「设备告警ioc数」字段(device_target_count)：按设备ID统计去重外联目标数，支持多日/单日日期范围，SQL级GROUP BY计算，同时新增HEAT_SORT_JOINS和SORT_FIELD_ALIASES映射支持SQL分页排序；(3)后端extract_iocs_from_text移除MD5/path提取，仅保留IP/域名/URL和设备ID；(4)IOC和设备ID展示改为textarea文本框，取消tag便签形式，用户可手动编辑，加「识别IOC」「识别设备ID」按钮手动触发提取；(5)告警页默认列重排为：设备ID/设备标签/设备告警ioc数/源ip/外联目标/端口/追踪/事件/威胁类型/APT组织/研判状态/外联目标热度；(6)事件管理页重构：点击创建事件→即时POST空白事件→左侧出现新空白事件卡片→右侧大框框编辑(名称/颜色/描述/设备textarea/ IOC textarea)，所有识别按钮手动触发，设备和IOC失焦自动diff-save |
| 2026-05-06 | 21 | review后修复与验证：研判工作台去除“隐藏已关闭”开关，事件仅按颜色显示；标签批次新增 `device_ids_snapshot` 快照，修复设备ID批次一键恢复（支持部分删除后恢复）；候选接口补齐 `threat_types` 筛选支持；Settings 页 TXT 批量打标成功提示改为读取后端 `imported` 返回；已执行 smoke regression、批次恢复定向测试和前端 build 验证通过 |
| 2026-05-06 | 22 | 前端 UI 视觉升级：重做应用壳层（品牌区、导航、顶部页头、主题切换），统一全局设计变量与 Element Plus 视觉覆盖；完整重建 Workbench / EventManager / AlertList / IocNotes 四个核心页面的标题区、筛选区、信息卡与表格容器样式，修复多处前端中文文案损坏；已执行 cmd /c npm run build 验证通过，当前仍有 Vite 大包体积 warning，功能不受影响 |
| 2026-05-06 | 23 | 导入体验修复+start-hide.bat：(1)导入详情Dialog新增行级明细——汇总统计卡片(成功/跳过重复/缺字段/失败)、Sheet列表含分状态计数、行明细表格支持按status筛选(parsed/skipped_duplicate/raw_only/failed)并展示错误原因+原始数据、下载失败CSV按钮；(2)导入历史表格新增「缺字段」列，跳过/缺字段/失败列均带问号tooltip解释含义；(3)删除导入时清理uploads目录下对应Excel文件+WAL checkpoint TRUNCATE+VACUUM回收SQLite磁盘空间；(4)新增start-hide.bat使用VBScript隐藏终端启动后端，3秒后自动打开浏览器；已执行npm run build验证通过 |
| 2026-05-06 | 24 | 导入体验按方案1继续收口：(1)后端 `/api/imports/{id}/rows` 新增 `status_group`，支持将 `raw_only+failed` 作为问题明细组、`skipped_duplicate` 作为跳过组查询；`/api/imports/{id}/failures.csv` 新增 `type=failures|skipped|raw_only`，CSV 补充 `device_id/target/port/status/error` 关键列；(2)Settings 导入详情改为两块清晰明细：失败/缺字段 与 跳过重复，直接显示行号、sheet、原因和关键列，并分别下载 CSV，不再依赖单表筛选；(3)删除导入保留 `wal_checkpoint(TRUNCATE)`，并改为按空闲页比例与回收体积判断是否执行 `VACUUM`，避免每次删除都强制全库压缩；(4)新增最小后端回归测试 `backend/tests/test_imports_helpers.py`，已执行 unittest、`py_compile` 与前端 build 验证通过 |
| 2026-05-07 | 25 | Workbench/Import/UI 收口：源 IP 列新增悬停预览全部源 IP；列宽与列显隐改为手动保存，避免拖拽时自动持久化导致卡顿；删除导入后仅执行 `wal_checkpoint(TRUNCATE)`，不再主动压缩 DB；移除 WebUI 中 `Event Operations`、`IOC Notes`、`Data & Config`、`Alert Archive` 英文眉标；已执行 `python -m unittest backend.tests.test_imports_helpers` 与 `npm run build` 验证通过。 |
| 2026-05-07 | 26 | 去除 App.vue 顶部重复页面说明 UI：对 `/events`、`/ioc-notes`、`/settings`、`/alerts` 四个路由停用公共 topbar 文案区域，仅保留各自页面内的 banner 与内容，避免”事件管理 / IOC 备注 / 导入与设置 / 原始告警”及其描述重复展示；已执行 `npm run build` 验证通过。 |
| 2026-05-08 | 阶段27 | UI 渐进式打磨上线：圆角克制化（dialog 22→12px / 按钮 12→8px / tag 999→6px / card 22→10px / input 12→8px），侧边栏精简（300→240px、去掉渐变光晕、紧凑品牌标识、底部色块切换、”Navigation”→”导航”），微动画系统（页面切换 fade+slide / 按钮:active scale 0.97 / 表格行 stagger 加载 keyframes / 骨架屏 shimmer / prefers-reduced-motion），表格优化（优先级行左侧 3px 色条替代整行着色 / 表头 font-weight 700→600 / cell-padding 缩小），统计数字缩小、上传图标缩小；全局 50+ CSS 规则，三主题兼容，build 验证通过 |
| 2026-05-08 | 阶段28 | 事件匹配重构+脚本修复：(1)事件匹配从设备ID改为IOC+端口匹配：`_event_maps_for_rows`移除device_id查询，仅保留IOC精确/通配映射；`_event_for_row`改为仅通过IOC+port匹配事件；(2)`generate_demo_data.py`新增`os.makedirs('uploads', exist_ok=True)`防止uploads目录不存在时报错；(3)`start-hide.bat`移除`del “%VBS_FILE%”`，修复VBScript异步执行时被立即删除导致启动失败的bug |
| 2026-05-08 | 阶段29 | v3.1 排序性能+表头筛选+列优化：(1)后端全量缓存：`query_alert_candidates` 首次加载全量查询+装饰并存入进程内缓存（10min TTL/LRU 20条），后续排序/翻页零DB查询（Python重排+切片）；新增 `_query_all_candidate_items` 全量取数函数；(2)resize/sort冲突修复：resize handle 固定在单元格右边框（right:-1px, 8px热区），`@mousedown.stop.prevent`+`stopPropagation()`；(3)研判状态改为纯展示（数据库什么显示什么，空值显示`-`）；(4)Excel风格表头筛选：7列支持表头下拉筛选（设备标签/威胁类型/APT组织/优先级/端口/徽章/ioc备注），computed过滤displayData，筛选不触发后端请求，换页条件保持；(5)原始告警新增「首次告警时间」「最近告警时间」列；(6)上传进度条：axios `onUploadProgress` 实时百分比 + 处理阶段计数器轮询（已处理X/共Y行）+ el-progress 条；(7)全量缓存SQLite表达式树溢出修复：`_source_ip_maps_for_rows` 改用简单GROUP BY替代OR拼接，25k行全量装饰不再报错；已执行 `npm run build` 验证通过 |
| 2026-05-08 | 阶段30 | 研判工作台排序回归+设备ID hash 提取修复：补回 Workbench 的 `analysis_status` / `is_focused` 表头排序按钮，并在后端候选排序映射中新增 `source_ip` / `analysis_status` / `is_focused` 支持；`extract_iocs_from_text` 调整为在出现”设备ID / device id”后连续提取同一段内所有 hash，允许无上下文独立行，遇到 `MD5` / `SHA1` 行立即停止；新增 3 组后端回归测试，并执行 `python -m unittest backend.tests.test_event_extraction backend.tests.test_workbench_sort_columns backend.tests.test_candidate_sorting backend.tests.test_filter_options` 与 `npm run build` 验证通过。 |
| 2026-05-09 | 阶段31 | 平台更新与数据迁移系统：(1)根目录新增 `VERSION`（版本号）和 `CHANGELOG.md`（变更日志）；(2)`backend/alembic/` 完整 Alembic 迁移框架——`alembic.ini` 配置、`env.py` 环境、`versions/001_baseline_v31.py` 基线迁移（13张表+16索引）；(3)新增 `GET /api/version` 接口，返回版本号、git commit、远程仓库、更新状态；(4)前端 Settings 页新增「系统信息」Tab：版本信息、变更日志展示、检查更新、数据管理入口；(5).gitignore 更新，排除 `backups/` 目录，保留 `CLAUDE.md` 为协作文件；(6)代码更新与数据迁移完全分离——代码走 git，数据永远本地；(7)初始化 git 仓库并完成首次提交（75 files） |
| 2026-05-09 | 阶段32 | 混合模式一键升级系统：(1)新增`一键打包.bat`（开发侧）——读取版本号、自动递增建议、前端构建、robocopy排除敏感目录、PowerShell打包为releases/下zip文件；(2)新增`一键上传.bat`（开发侧）——git status展示变更、交互式提交说明、git add/commit/push、自动创建并推送版本标签；(3)新增`upgrade.bat`（正式侧）——自动备份DB（wmic时间戳）、双通道升级检测（优先ZIP离线包，回退Git pull模式）、robocopy安全覆盖（排除data/uploads/backups/venv/node_modules）、依赖自动安装+前端构建、版本确认提示；(4)删除`start-hide.bat`和旧`update.bat`文件；(5)`.gitignore`新增`releases/`排除规则；(6)所有bat文件统一`@echo off`+`chcp 65001`+`setlocal enabledelayedexpansion`，robocopy退出码正确判断（errorlevel>7才算失败） |
| 2026-05-09 | 阶段33 | 升级脚本Python化：将`一键打包.bat`/`一键上传.bat`/`upgrade.bat`转换为Python脚本（`pack_release.py`/`push_release.py`/`upgrade.py`），彻底解决Windows批处理文件编码乱码问题；(1)`pack_release.py`——版本读取/递增建议、npm构建、shutil复制排除敏感目录、zipfile打包；(2)`push_release.py`——git变更检测、交互式提交、push远程、版本标签创建推送；(3)`upgrade.py`——DB备份（时间戳命名）、双通道升级（ZIP离线包优先/Git pull回退）、venv依赖安装、前端构建；(4)删除全部旧.bat文件 |