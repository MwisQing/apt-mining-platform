# Changelog

## v4.0.0 - 2026-05-21

### Go 全栈重写

**为什么重写：** v3.x 累计 82 个阶段补丁后架构复杂度超过可维护上限，性能瓶颈（SQLite 单连接阻塞、快照+实时覆盖不一致、导入卡死）无法通过增量修复解决。换 Go + PostgreSQL 强制从头设计，切断补丁惯性。

### 后端

- 新增：Go 1.22 + Gin 项目结构，handler / service / repository / model 四层架构
- 新增：PostgreSQL 替代 SQLite，14 张表 + GIN 全文搜索索引 + 候选部分索引
- 新增：候选查询 CTE SQL（1 条 SQL 搞定评分/Badge/热度聚合），替代 v3.x 14 次 SQL + Python 装饰
- 新增：Excel 流式导入（goroutine 后台顺序处理，每 500 行 batch commit），不阻塞查询
- 新增：事件 CRUD + IOC 自动提取 + 设备关联
- 新增：标签批次管理 + TXT 批量打标 + 设备标签
- 新增：IOC 追踪管理
- 新增：配置读写 + 词典加载
- 新增：健康检查 + 版本信息接口
- 删除：snapshot_builder.py（1246 行）、快照查询路径、候选缓存管理、patch_snapshot_for_* 增量刷新
- 删除：SQLite StaticPool、QueuePool、WAL checkpoint 等兼容代码

### 前端

- 新增：5 个页面对接 Go 后端（Workbench / EventManager / AlertList / Settings / IocNotes）
- 新增：列配置文件化（columns.json）
- 保留：三主题切换（暗色/VSCode 浅色/VS2026 蓝色）
- 保留：表头筛选、列宽拖拽、排序按钮
- 保留：Excel 风格上传、导入详情、失败行下载

### 运维

- 新增：`startGo.bat` / `stopGo.bat` 正式实例（8088）
- 新增：`startGoTest.bat` / `stopGoTest.bat` 测试实例（9099）
- 新增：`init_db.bat` PostgreSQL 初始化
- 新增：`go_import_and_start.bat` Go 依赖导入+启动一键完成
- 删除：全部 Python 运维脚本（start.py / stop.py / install.py / upgrade.py / pack_release.py / push_release.py）

---

## v3.3.x（Python/FastAPI 旧版，已停止维护）

历史变更记录已归档。v3.x 共经历 82 个迭代阶段（阶段0~82），涵盖前端重建、性能优化、快照表方案、导入体验改进等工作。详见 git 历史。
