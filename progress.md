# 快照预计算 v3 进度

## 2026-05-15 本次会话

- 已读取 `CLAUDE.md`、`task_plan.md`、`findings.md`、`progress.md`。
- 已将目标改为修复研判工作台事件显示，并把快照一致性风险作为本次收敛重点。
- 已在 `backend/api/alerts.py` 增加快照结果的实时关系覆盖层，返回前补齐事件、设备标签、IOC 备注/追踪状态，并重算相关徽章、原因、分数和优先级。
- 已在 `backend/tests/test_snapshot_query_semantics.py` 增加“旧快照未 patch 但实时事件存在”的回归测试；专项测试 `python -m unittest backend.tests.test_snapshot_query_semantics` 6 项通过。
- 已移除事件变更后的无条件后台全量快照重建，避免事件写入后再被异步快照切换制造竞态。
- 验证通过：`py_compile`、快照相关 unittest 29/29、后端全量 unittest 54/54、前端 `npm run build`。
- 已更新 `CLAUDE.md` 阶段72进度记录。
- 用户反馈点击创建事件卡死后，已确认当前 `Workbench.vue` 源码缺失创建事件按钮和弹窗，后端事件创建仍存在同步快照 patch 耗时风险。
- 已恢复工作台操作列、创建事件按钮和 Dialog，提交时自动带入当前行 IOC/端口/设备，并在成功后本地即时回填事件状态。
- 已把事件变更后的快照 patch 改为提交后后台 best-effort 执行，不再阻塞创建事件请求。
- 验证通过：`py_compile`、快照相关 unittest 22/22、后端全量 unittest 54/54、前端 `npm run build`。
- 已更新 `CLAUDE.md` 阶段73进度记录。

## 2026-05-15 09:51:08

- 已读取 `CLAUDE.md` 与 `PRECOMPUTE_DESIGN_v3.md`。
- 已确认当前候选接口实际仍走实时查询，快照 v3 代码半落地。
- 已创建本地计划文件，准备进入修复。

## 2026-05-15 10:05

- 后端候选接口已接回 active snapshot 查询路径，失败时记录日志并回退实时查询。
- 事件、IOC 备注、标签变更改为同一事务内 patch 快照后再提交。
- 新增事件 scope 级重算，事件删除/移除 IOC/移除设备后会按当前全局事件重新匹配。
- 标签删除空列表时会清空快照 tag 子表；标签颜色变更会刷新主表 JSON。
- Settings 导入完成后的快照轮询函数已补回，避免未定义变量/函数。
- 已补齐 `httpx` 依赖；快照专项测试 `backend.tests.test_snapshot_precompute backend.tests.test_snapshot_query_semantics` 21 项通过。

## 2026-05-15 10:10

- 后端全量测试 `python -m unittest discover backend/tests` 53 项通过。
- 前端 `npm run build` 通过。
- 已启动本地服务 `http://127.0.0.1:8090`，`/api/health` 返回 `{"status":"ok"}`。
- 已更新 `CLAUDE.md` 阶段70进度记录。
