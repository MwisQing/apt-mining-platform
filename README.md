# APT Mining Workbench

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![Vue 3](https://img.shields.io/badge/Vue-3.x-brightgreen.svg)](https://vuejs.org/)

安全分析师从海量网络告警中挖掘 APT（高级持续性威胁）事件的单机离线工作台。

> 每天面对10万+告警，自动化筛选候选、评分排序、去重聚合，把真正需要人类研判的事件从噪声中捞出来。

## 为什么做这个

安全运营中，告警量巨大但真正有价值的不足1%。现有方案要么是重型SIEM/SOAR平台（部署复杂、成本高），要么是手工脚本（不可维护）。这个项目提供一种**中间路线**：

- **单机离线**：一个 `start.bat` 就能跑，不依赖外部服务
- **智能评分**：SQL 级别的候选评分 + 去重，10万条数据秒级分页
- **研判闭环**：从告警导入 → 候选筛选 → 创建事件 → 标记IOC → 下次自动追踪

## 功能演示

| 首页-研判工作台 | 事件管理 | 导入与设置 |
|:---:|:---:|:---:|
| 候选评分排序、去重、标签、IOC备注 | 创建事件、关联设备/IOC、跟进记录 | Excel导入、词典配置、标签批次 |

## 快速开始

### 环境要求

- **Python** 3.10+
- **Node.js** 18+（仅开发/构建时需要，纯运行可用预构建的 `frontend/dist/`）

### 一键安装（Windows）

双击 `install.bat`，自动完成虚拟环境创建、Python 依赖安装、前端依赖安装和构建。

### 手动安装

```bash
# 1. Python 虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. 前端（可选：如果 frontend/dist/ 已存在可跳过构建）
cd frontend
npm install
npm run build
cd ..
```

### 启动

```bash
# Windows
双击 start.bat

# Linux / macOS
source venv/bin/activate
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8088
```

浏览器访问 `http://127.0.0.1:8088`

### 开发模式

```bash
# 后端（终端1）
source venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8088 --reload

# 前端（终端2）
cd frontend
npm run dev  # Vite 开发服务器，自动代理 API 到 8088
```

## 用户工作流

```
┌─────────────────────────────────────────────────────────────┐
│  1. 上传告警 Excel（10万+行）→ 导入平台                       │
│  2. 导入设备标签 TXT → 批量打标（排查成功/重点设备/不好查）      │
│  3. 研判工作台 → 候选结果（自动筛 APT/远控、评分排序、去重）      │
│  4. 逐条研判：有价值 → 创建事件 │ 已知 → 标记 IOC 备注         │
│  5. 下次导入新数据 → 标签和追踪自动生效                        │
└─────────────────────────────────────────────────────────────┘
```

## 候选评分引擎

平台在 SQL 层面完成评分，支持分页排序，10万+数据无压力：

### 基础命中分

| 规则 | 触发条件 | 得分 |
|------|----------|------|
| 威胁类型命中 APT | `threat_type` 包含 `apt` | 34 |
| 威胁类型命中远控 | `threat_type` 包含 `远控` / `remote` | 30 |
| 已映射标准 APT 组织 | `std_apt_org` 非空 | 26 |
| 原始 APT 组织非空 | `apt_org` 非空 | 22 |
| 情报标签命中 | `intel_tags` 包含 `apt` / `c2` / `远控` | 18 |

### 加分 / 减分项

- **加分**：威胁等级（最高18）、APT 分级（最高16）、目标热度（最高18）、设备热度（最高24）、源IP热度（最高14）、多厂商命中（最高9）、事件关联（+6）、设备标签（最高+8）
- **减分**：已追踪活跃 -12、追踪过期 -4

### 优先级

| 分数 | 标签 | 颜色 |
|------|------|------|
| ≥ 110 | 高优先 | 红 |
| ≥ 75 | 中优先 | 橙 |
| < 75 | 观察 | 灰 |

### Badge 标记

自动为候选打上可视化标记：APT词典、高级黑灰产、噪声家族、多厂商、跨天持续、横向扩散、追踪过期、高级别、疑似扫描。

## 项目结构

```
apt-mining-platform/
├── backend/                    # FastAPI 后端
│   ├── main.py                 # 入口，路由挂载 + SPA fallback
│   ├── api/                    # API 路由
│   │   ├── alerts.py           # 告警列表 + 候选结果（核心接口）
│   │   ├── events.py           # 事件 CRUD + IOC/设备关联
│   │   ├── tags.py             # 标签批次 + 设备标签
│   │   ├── traced.py           # IOC 备注追踪
│   │   ├── imports.py          # Excel 导入（异步线程）
│   │   ├── devices.py          # 设备列表
│   │   ├── config.py           # 配置读写
│   │   └── persistence.py      # 跨天持续外联
│   ├── models/                 # SQLAlchemy 模型
│   ├── services/               # Badge 引擎 + 候选评分/规则/哈希
│   └── utils/                  # 配置/词典加载 + DB 引擎
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── views/              # 5 个页面
│   │   │   ├── Workbench.vue   # 研判工作台（核心）
│   │   │   ├── AlertList.vue   # 原始告警列表
│   │   │   ├── EventManager.vue # 事件管理
│   │   │   ├── Settings.vue    # 导入与设置
│   │   │   └── IocNotes.vue    # IOC 备注管理
│   │   ├── api/                # axios 封装
│   │   ├── composables/        # 组合式函数（列配置等）
│   │   └── router/             # Vue Router
│   └── dist/                   # 生产构建产物
├── config/                     # 配置文件
│   ├── config.yaml             # 主配置（评分参数、Badge 阈值）
│   ├── apt_org_dict.yaml       # APT 组织词典
│   ├── advanced_crime.yaml     # 高级黑灰产词典
│   └── noise_family.yaml       # 噪声家族词典
├── generate_demo_data.py       # 演示数据生成器（10万条模拟告警）
├── requirements.txt            # Python 依赖
├── install.bat                 # Windows 一键安装
├── start.bat                   # Windows 一键启动
├── stop.bat                    # Windows 停止
└── README.md
```

## 核心 API

### 告警与候选

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/alert-candidates` | **候选结果（核心）**：支持日期/类型/标签/威胁等级/APT分级/关键词筛选，SQL级评分排序分页 |
| GET | `/api/alerts` | 原始告警列表（分页、筛选、Badge） |
| GET | `/api/alerts/options` | 动态筛选选项 |
| POST | `/api/alerts/export` | 导出告警 xlsx |

候选结果返回字段亮点：`candidate_score`（评分）、`candidate_priority`（优先级）、`candidate_reasons`（命中原因）、`badges`（徽章）、`heat`（热度统计）、`device_tags`（设备标签）、`trace_status`（IOC追踪状态）、`event`（关联事件）、`source_ips`（聚合源IP）、`ioc_note`（IOC备注）。

### 事件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/events` | 事件列表 / 创建 |
| GET/PATCH/DELETE | `/api/events/{id}` | 事件 CRUD |
| POST | `/api/events/{id}/followups` | 添加跟进记录 |
| POST | `/api/events/{id}/devices` | 关联设备 |
| POST | `/api/events/{id}/iocs` | 关联 IOC |
| POST | `/api/events/extract-iocs` | 从文本中智能提取 IOC 和设备 ID |

### 标签系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/tags/batches` | 批次列表 / 创建 |
| POST | `/api/tags/batches/import-text-files` | TXT 批量打标 |
| DELETE | `/api/tags/batches/{id}` | 软删除批次 |
| POST | `/api/tags/batches/{id}/restore` | 一键恢复批次 |
| POST | `/api/tags/devices/batch` | 批量设备打标 |
| GET/POST/DELETE | `/api/tags/devices/{id}/tags` | 单设备标签 CRUD |

### 追踪 / 导入 / 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/traced` | IOC 备注列表 / 添加 |
| PATCH/DELETE | `/api/traced/{id}` | 更新 / 删除 IOC 备注 |
| POST/GET | `/api/imports` | 上传 Excel / 导入历史 |
| GET/DELETE | `/api/imports/{id}` | 导入详情 / 删除 |
| GET/POST | `/api/config` | 读/写配置 |
| GET | `/api/health` | 健康检查 |

## 数据库

SQLite，WAL 模式，每30分钟自动 TRUNCATE checkpoint。首次启动自动建表。

| 表名 | 说明 |
|------|------|
| `alerts` | 告警主表（含评分字段、Badge 标记、Import 溯源） |
| `mined_events` | 挖掘事件 |
| `mined_event_devices` | 事件-设备关联 |
| `mined_event_iocs` | 事件-IOC 关联 |
| `event_followups` | 事件跟进记录 |
| `tags` | 标签定义 |
| `tag_batches` | 标签批次（含软删除 status 字段） |
| `device_tags` | 设备-标签关联 |
| `traced_targets` | IOC 备注追踪库 |
| `imports` / `import_sheets` / `import_rows` | 导入溯源（三级） |
| `audit_log` | 操作审计日志 |

## 演示数据

运行 `generate_demo_data.py` 生成 10 万条模拟告警数据（含 APT 组织、C2 通信、远控木马等模式）：

```bash
source venv/bin/activate
python generate_demo_data.py
```

生成的 Excel 文件在 `uploads/` 目录，可通过「导入与设置」页面上传体验。

## 技术选型

| 层 | 技术 | 选型理由 |
|----|------|----------|
| 后端框架 | FastAPI | 高性能异步、自动 OpenAPI 文档 |
| ORM | SQLAlchemy 2.0 | 成熟稳定、原生 SQL 能力强 |
| 数据库 | SQLite (WAL) | 零配置、单机友好、10万级无压力 |
| 前端框架 | Vue 3 (Composition API) | 轻量、响应式、生态完善 |
| 构建工具 | Vite 6 | 极速 HMR、开箱即用 |
| UI 库 | Element Plus | 企业级组件、中文友好 |
| 数据处理 | Pandas + OpenPyXL | Excel 解析、批量导入 |

## 设计原则

1. **后端不常改**：评分、去重、Badge 全部 SQL 级完成，前端对接 API 即可，不需要动后端代码
2. **单文件数据库**：SQLite WAL 模式，自带备份只需复制 `data/` 目录
3. **无状态前端**：Vue 3 纯 Composition API，无 Vuex/Pinia，状态通过 API 实时获取
4. **生产即开发**：`npm run build` 产物直接挂载到 FastAPI，不需要 Nginx

## 已知限制

- **单机设计**：不支持多用户并发写入（SQLite 写锁），适合分析师个人使用
- **Windows 优先**：启动脚本为 `.bat`，Linux/macOS 用户使用命令行
- **Excel 导入**：支持 `.xlsx` 格式，字段名通过别名自动映射（支持中英文表头）
- **数据规模**：10-50万条告警流畅运行，百万级以上建议迁移到 PostgreSQL

## License

MIT

## 贡献

欢迎提交 Issue 和 Pull Request。本项目为安全分析师的日常工作效率工具，任何有助于提升研判效率的改进都欢迎讨论。
