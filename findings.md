# 快照预计算 v3 发现记录

## 2026-05-15 本次事件显示问题

- 用户反馈：事件没有显示到研判工作台，怀疑和快照表有关；核心诉求是平台好用，而不是继续制造快照一致性问题。
- 处理原则：快照适合承载大量告警的静态候选字段，事件/标签/追踪等人工研判状态必须优先保证实时一致。
- 根因方向确认：`/api/alert-candidates` 有 active snapshot 时直接返回 `event_json/device_tags_json/trace_json`，如果增量 patch 漏掉或异步重建未完成，前端 `Workbench.vue` 只能看到旧 JSON，因此事件不会显示。
- 修复策略：在快照查询分页结果返回前，使用实时 `mined_event_*`、`device_tags/tags`、`traced_targets` 表覆盖当前页关系字段，并重新计算这些关系影响的状态、徽章、原因、分数和优先级。
- 继续排查“点击创建事件卡死”时发现：当前 `frontend/src/views/Workbench.vue` 源码没有创建事件按钮/弹窗/import，只有事件展示列；`columns.json` 也没有操作列。这说明创建事件流程在源码中已经回退/丢失，或者用户点到的是旧打包残留。
- 后端 `create_event` 仍同步调用 `_patch_snapshot_for_event`，大数据量下可能让提交等待快照增量刷新；由于快照查询已实时覆盖事件状态，事件写入不应再阻塞在快照 patch 上。

## 2026-05-15

- `PRECOMPUTE_DESIGN_v3.md` 标记为“待开发”，但部分实现已经进入代码库。
- 当前 `/api/alert-candidates` 主入口仍走实时 `_query_candidate_items`，返回 `snapshot_status="live"`。
- `_query_from_snapshot`、`_snapshot_row_to_response`、`_build_snapshot_filter_options_v3` 已存在，但未接入主入口。
- 阶段 69 记录显示：此前因快照刷新后设备标签、事件、IOC 备注不显示，查询被改回实时。
- 事件/标签/IOC 的 patch wrapper 在业务 commit 后执行，失败只记日志，不符合文档“同一事务失败回滚”的描述。
- `POST /api/tags/batches/import-text-files` 当前只清候选缓存，未 patch 受影响设备。
- `POST /api/traced/import` 当前只 patch 最后一个 target/port。
- `frontend/src/views/Settings.vue` 调用了 `snapshotCheckStarted` 和 `startSnapshotCheck`，但当前文件里没有定义或导入。
- 快照 unittest 运行失败，因为 `requirements.txt` 缺少 `httpx`。
