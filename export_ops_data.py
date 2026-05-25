#!/usr/bin/env python3
"""导出运营数据（事件、IOC备注、标签、配置），文件极小适合远程迁移。

用法：
    python export_ops_data.py          # 默认导出到 ops-export.json
    python export_ops_data.py --output my-export.json
"""
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/workbench.db")
TABLES = {
    # 核心运营数据
    "mined_events":       "事件主表",
    "mined_event_devices": "事件-设备关联",
    "mined_event_iocs":   "事件-IOC关联",
    "event_followups":    "事件跟进记录",
    "traced_targets":     "IOC追踪/备注",
    "tags":               "标签",
    "tag_batches":        "标签批次",
    "device_tags":        "设备标签关联",
    "imports":            "导入记录",
    "import_sheets":      "导入Sheet",
    "config_data":        "系统配置",
}


def main():
    output = "ops-export.json"
    if len(sys.argv) > 2 and sys.argv[1] == "--output":
        output = sys.argv[2]

    if not DB_PATH.exists():
        print(f"[ERROR] 数据库不存在: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    export = {"version": "1.0", "tables": {}}

    for table, desc in TABLES.items():
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            export["tables"][table] = [dict(r) for r in rows]
            print(f"  {desc} ({table}): {len(rows)} 条")
        except Exception as e:
            print(f"  {desc} ({table}): 跳过 ({e})")

    conn.close()

    with open(output, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    import os
    size = os.path.getsize(output)
    print(f"\n导出完成: {output} ({size / 1024:.1f} KB)")
    print("将此文件复制到新服务器，运行 import_ops_data.py 导入。")


if __name__ == "__main__":
    main()
