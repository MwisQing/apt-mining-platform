# 研判工作台性能问题分析与改造建议

日期：2026-05-11

适用范围：APT Mining Platform 研判工作台 `/api/alert-candidates`

目标读者：接手评估和开发的后端/架构团队

---

## 1. 问题

当前“研判工作台”存在明显性能问题：

- 首次打开工作台或首次切换某些顶部筛选条件时，接口返回很慢
- 已完成一次全量预热后，仅切换日期会明显变快
- 用户预期是“先选定日期后，再基于当天结果做进一步筛选”，但当前并不完全满足

### 用户侧体感

- 首次加载很慢，接近不可接受
- 改日期后很快
- 改“目标类型 / 标签 / 威胁类型 / 是否隐藏已追踪”等条件时，仍会再次变慢

---

## 2. 当前结论

### 结论一：不是 FastAPI 框架本身慢

当前主要耗时不在 Web 框架层。

### 结论二：也不主要是 SQLite SQL 本身慢

SQL 阶段有耗时，但不是主瓶颈。当前主瓶颈是：

**首次请求时，对 9 万多条候选结果在 Python 层做全量装饰、关系拼接、badge 计算、评分、摘要生成。**

### 结论三：当前架构属于“请求时全量计算”，而不是“导入时预计算、请求时只查询”

这才是导致首次加载慢的根本原因。

---

## 3. 实测数据

### 数据规模

- `alerts` 总告警数：`200000`
- 研判工作台候选去重后分组数：`92512`
- `traced_targets`：`0`
- `device_tags`：`3`
- `tags`：`3`
- `mined_event_iocs`：`1`
- `mined_events`：`1`

说明：

- 即使追踪、标签、事件数据非常少，首次工作台加载依然很慢
- 这进一步说明慢点不是关系表本身，而是全量候选装饰链路

### 首次候选预热分阶段耗时

以下为对 `backend/api/alerts.py` 候选生成链路拆分后的实测：

- `dedup_sql_fetch`：`2.077s`
- `cross_day_lateral`：`0.513s`
- `heat_and_source_maps`：`0.901s`
- `event_maps`：`0.175s`
- `trace_maps`：`0.176s`
- `device_tag_map`：`0.068s`
- `make_items`：`83.818s`
- `decorate_total`：`109.542s`

### 首次 / 二次请求对比

- 第一次请求：`94.19s`
- 第二次仅切换日期：`0.062s`

结论：

- SQL 读取和聚合只占几秒
- 绝大部分时间消耗在 Python 层逐条构造候选数据

---

## 4. 现有实现行为

相关文件：

- [backend/api/alerts.py](C:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-3.1.4\apt-mining-platform-3.1.4\backend\api\alerts.py)
- [backend/services/__init__.py](C:\Users\Seria\Desktop\ai开发\apt-mining-platform\apt-mining-platform-3.1.4\apt-mining-platform-3.1.4\backend\services\__init__.py)

### 当前缓存行为

当前 `/api/alert-candidates` 已做过一轮优化：

- 对基础筛选条件建立 `_full_cache`
- 首次构建全量候选集
- 改日期、关键字、目标类别、badge 时，在缓存结果上做内存过滤

### 当前仍然会触发“新桶预热”的条件

以下条件仍属于“基础候选集”的组成部分，修改时会生成新的缓存桶：

- `target_type`
- `device_tags`
- `exclude_device_tags`
- `threat_types`
- `threat_levels`
- `apt_tiers`
- `hide_traced`
- `hide_closed`
- `alert_count_max`

因此当前系统表现为：

- 改 `date/keyword/target_kind/badges`：快
- 改上述“基础条件”：第一次仍慢

这与用户预期不一致。

---

## 5. 代码级根因

### 5.1 首次候选集构建规模过大

当前候选接口会先对告警做去重，形成 9.25 万条候选组，然后在 Python 层继续处理。

关键位置：

- `_query_all_candidate_items(...)`
- `_decorate_candidate_items(...)`
- `_make_items(...)`

### 5.2 Python 全量装饰是绝对主瓶颈

`_make_items(...)` 和 `_decorate_candidate_items(...)` 中，逐条做了以下事情：

- 事件关系匹配
- 追踪关系匹配
- 设备标签拼接
- badge 生成
- 候选命中规则识别
- candidate score 计算
- priority 分类
- heat summary / relation summary / candidate summary 拼接
- 排序辅助字段构造

以上都发生在请求期，而不是导入期。

### 5.3 当前不是“先按日期缩小再筛选所有条件”

从交互角度看，用户会自然认为：

1. 先按日期把范围缩到当天
2. 再在当天数据内继续筛选威胁类型、标签、目标类型等

但当前实现里，只有部分条件是“后过滤”，剩余条件仍参与“基础候选集生成”。

所以用户改某些条件时，还是会再次走一遍新的大规模候选构建。

### 5.4 SQLite 不是第一根因，但当前模型对 SQLite 不友好

虽然 SQL 不是当前第一瓶颈，但当前架构存在以下问题：

- 单次处理分组数非常大
- 多阶段结果依赖 Python 逐条装饰
- 首屏请求承担了本该由离线或导入阶段承担的工作

即使换成 PostgreSQL，如果仍保留“请求时全量 Python 装饰”，首次加载仍然不会优秀。

---

## 6. 为什么 VT / 威胁情报平台可以接近 1s

不是因为它们用了某个“更快的 Web 框架”。

通常是因为它们采用了以下能力：

- 预计算
- 物化结果
- 增量更新
- 常驻热缓存
- 搜索/分析型存储
- 请求时仅做筛选、排序、分页

换句话说：

**成熟平台是“请求期查结果”，当前项目是“请求期算结果”。**

---

## 7. 当前方案的阶段性价值与边界

### 已完成优化的价值

本轮已完成的优化解决了两个问题：

1. 同一基础条件下切换日期非常快
2. 大数据量下避免了 SQLite `too many SQL variables`

### 当前方案的边界

当前优化只是“中间态”，不是最终架构：

- 首次预热仍慢
- 改基础筛选条件仍慢
- 首屏仍不是秒级

因此当前方案只能视为：

**把“日期切换慢”修好了，但没有从根上解决“首次候选构建慢”。**

---

## 8. 推荐方案

### 推荐等级 A：候选快照表 / 物化结果表

这是推荐主方案。

核心思想：

- 告警导入完成后，不在用户请求时计算候选
- 由后台任务或导入后流程，提前生成“候选快照表”
- 页面请求时只做：
  - `WHERE 日期`
  - `AND 顶部筛选条件`
  - `ORDER BY`
  - `LIMIT/OFFSET`

### 建议新增的数据层

新增表，例如：

- `alert_candidates_snapshot`

建议字段至少包括：

- `candidate_key` 或 `(device_id, target, port)`
- `device_id`
- `target`
- `target_type`
- `target_kind`
- `port`
- `source_ips`
- `source_ip_count`
- `threat_type`
- `threat_level`
- `std_apt_org`
- `apt_org`
- `apt_org_tier`
- `alert_count`
- `first_alert_time`
- `last_alert_time`
- `candidate_score`
- `candidate_priority`
- `heat_target_alert_count`
- `heat_target_device_count`
- `heat_device_alert_count`
- `heat_device_target_count`
- `event_status`
- `trace_status`
- `ioc_note`
- `badges_json`
- `device_tags_json`
- `candidate_reasons_json`
- `updated_at`

### 更新时机

候选快照应在以下时机增量刷新：

- 导入告警完成后
- 标签变更后
- 追踪库变更后
- 事件 IOC 变更后
- 配置或 badge 规则变更后

### 请求链路变化

当前：

- 请求 → 去重 → 聚合 → 拼关系 → 计算评分 → 排序 → 分页

推荐改为：

- 导入/变更后异步刷新快照
- 请求 → 直接查快照表 → 排序 → 分页

### 预期收益

- 首次打开无需全量 Python 装饰
- 改日期和其他顶部筛选都应接近秒级
- 筛选语义更符合用户预期
- 更容易做进一步索引优化

---

## 9. 备选方案

### 方案 B：把更多筛选条件继续下沉为缓存后的内存过滤

思路：

- 继续扩大 `_full_cache` 的覆盖面
- 把 `target_type / device_tags / threat_types / hide_traced` 等也改为后过滤

优点：

- 改动相对小
- 用户交互体感会进一步改善

缺点：

- 首次全量预热依然很慢
- 内存占用会更大
- 数据口径会越来越依赖缓存时机
- 架构复杂度会上升，不适合作为长期方案

结论：

可作为过渡，不推荐作为最终方案。

### 方案 C：直接更换数据库

例如：

- PostgreSQL
- ClickHouse
- Elasticsearch

优点：

- 后续扩展空间更大

缺点：

- 如果不改变“请求时全量 Python 装饰”的设计，收益有限

结论：

**换库不是第一优先级。**
应优先改“计算时机”，再决定是否换存储。

---

## 10. 推荐实施顺序

### 第一步

落候选快照表设计，确定唯一键、刷新口径、JSON 字段边界。

### 第二步

将当前 `_decorate_candidate_items(...)` 的结果结构拆分为：

- 可持久化字段
- 请求期轻量补充字段

### 第三步

在“导入完成”流程后增加候选快照构建任务。

### 第四步

在标签、追踪、事件变更后增加对应候选快照增量刷新逻辑。

### 第五步

将 `/api/alert-candidates` 改为直接查询快照表。

### 第六步

前端验证：

- 首次打开工作台
- 切换日期
- 切换目标类型
- 切换威胁类型
- 切换标签
- 打开隐藏已追踪
- 组合筛选

---

## 11. 验收标准建议

建议把性能验收标准明确下来：

- 首次打开研判工作台：`< 3s`
- 切换日期：`< 1s`
- 切换目标类型/威胁类型/标签：`< 1s`
- 翻页/排序：`< 1s`

如果目标是“接近 VT/威胁情报平台体验”，建议进一步压到：

- 首次：`1~2s`
- 后续筛选：`< 500ms`

---

## 12. 本次分析结论摘要

一句话总结：

**当前慢，不是 FastAPI 慢，不是 SQLite 先天不行，而是把 9 万多条候选的全量装饰、评分、关系拼接放在了首屏请求期。**

要真正接近 1s：

**必须从“请求时全量计算”改成“导入后预计算 / 增量刷新 / 请求时只查结果”。**

