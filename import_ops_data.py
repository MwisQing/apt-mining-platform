#!/usr/bin/env python3
"""导入运营数据（由 export_ops_data.py 导出）。

用法：
    python import_ops_data.py ops-export.json
"""
import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/workbench.db")


def main():
    if len(sys.argv) < 2:
        print("用法: python import_ops_data.py <json文件>")
        sys.exit(1)

    json_file = sys.argv[1]
    if not Path(json_file).exists():
        print(f"[ERROR] 文件不存在: {json_file}")
        sys.exit(1)

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not DB_PATH.exists():
        print(f"[ERROR] 数据库不存在: {DB_PATH}")
        print("请先运行 install.sh 初始化数据库。")
        sys.exit(1)

    conn = sqlite3.connect(str(DB_PATH))
    tables = data.get("tables", {})

    for table_name, rows in tables.items():
        if not rows:
            continue
        cols = list(rows[0].keys())
        placeholders = ",".join(["?" for _ in cols])
        col_list = ",".join(cols)

        count = 0
        for row in rows:
            values = [row.get(c) for c in cols]
            try:
                conn.execute(
                    f"INSERT OR REPLACE INTO {table_name} ({col_list}) VALUES ({placeholders})",
                    values,
                )
                count += 1
            except Exception as e:
                print(f"  插入 {table_name} 失败: {e}")

        conn.commit()
        print(f"  {table_name}: 导入 {count} 条")

    conn.close()
    print("\n导入完成。重启服务即可。")


if __name__ == "__main__":
    main()
