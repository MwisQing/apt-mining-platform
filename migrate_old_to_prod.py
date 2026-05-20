#!/usr/bin/env python3
"""从旧版本 SQLite 库迁移关系数据到 PostgreSQL 正式库（纯 psql 实现，避开 psycopg2 编码问题）。"""
import sqlite3
import subprocess
import os
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OLD_DB = str(SCRIPT_DIR / "旧版本的测试平台数据" / "data" / "workbench.db")
PG_BIN = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"
PG_DB = "apt_mining_prod"
PG_USER = "postgres"
PG_PASS = "562245610"

TABLES = [
    "tag_batches", "tags", "device_tags", "traced_targets",
    "mined_events", "mined_event_devices", "mined_event_iocs", "event_followups",
]


def run_psql(sql):
    """执行 psql SQL 命令。"""
    env = os.environ.copy()
    env["PGPASSWORD"] = PG_PASS
    result = subprocess.run(
        [PG_BIN, "-h", "127.0.0.1", "-U", PG_USER, "-d", PG_DB, "-c", sql],
        env=env, capture_output=True, text=True,
    )
    return result


def run_psql_multi(sql_lines):
    """执行多行 SQL（通过 stdin）。"""
    env = os.environ.copy()
    env["PGPASSWORD"] = PG_PASS
    result = subprocess.run(
        [PG_BIN, "-h", "127.0.0.1", "-U", PG_USER, "-d", PG_DB],
        env=env, input=sql_lines, capture_output=True, text=True,
    )
    return result


def get_pg_columns(table):
    """获取 PG 表的列信息。"""
    r = run_psql(
        f"SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema='public' AND table_name='{table}' "
        f"AND is_identity='NO' ORDER BY ordinal_position;"
    )
    cols = [line.strip() for line in r.stdout.strip().split("\n") if line.strip() and line.strip() != "column_name"]
    return cols


def get_pg_data_types(table):
    """获取 PG 表的列数据类型。"""
    r = run_psql(
        f"SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_schema='public' AND table_name='{table}' ORDER BY ordinal_position;"
    )
    types = {}
    for line in r.stdout.strip().split("\n"):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 2:
            types[parts[0]] = parts[1]
    return types


def migrate_table(table, sqlite_cur, pg_types):
    """迁移单表。"""
    # SQLite 列
    sqlite_cur.execute(f"PRAGMA table_info({table})")
    sqlite_cols = [r[1] for r in sqlite_cur.fetchall()]
    if not sqlite_cols:
        return 0

    # PG 列
    pg_cols = get_pg_columns(table)
    common_cols = [c for c in sqlite_cols if c in pg_cols]
    if not common_cols:
        print(f"  {table}: 无共有列，跳过")
        return 0

    # 查数据
    col_sql = ", ".join(f'"{c}"' for c in common_cols)
    sqlite_cur.execute(f"SELECT {col_sql} FROM {table}")
    rows = sqlite_cur.fetchall()
    if not rows:
        print(f"  {table}: 空表，跳过")
        return 0

    # 构造 INSERT VALUES
    values_list = []
    for row in rows:
        vals = []
        for i, val in enumerate(row):
            col = common_cols[i]
            dtype = pg_types.get(col, "text")
            if val is None:
                vals.append("NULL")
            elif isinstance(val, (int, float)):
                vals.append(str(val))
            elif dtype in ("bigint", "integer", "smallint", "real", "double precision", "numeric"):
                try:
                    vals.append(str(int(val)))
                except (ValueError, TypeError):
                    vals.append("NULL")
            else:
                v = str(val).replace("'", "''")
                vals.append(f"'{v}'")
        values_list.append("(" + ", ".join(vals) + ")")

    pg_col_list = ", ".join(f'"{c}"' for c in common_cols)
    sql = f"INSERT INTO {table} ({pg_col_list}) VALUES {', '.join(values_list)} ON CONFLICT DO NOTHING;"

    r = run_psql_multi(sql)
    count = 0
    for line in r.stdout.split("\n"):
        if "INSERT 0" in line:
            try:
                count = int(line.split()[-1])
            except (ValueError, IndexError):
                count = len(rows)
            break

    if r.returncode != 0:
        print(f"  {table}: 部分失败 (返回码 {r.returncode})")
        if count == 0:
            count = len(rows)  # 至少尝试了这些
    else:
        if count == 0:
            count = len(rows)

    print(f"  {table}: {count}/{len(rows)} 条")
    return count


def fix_sequences():
    """对齐序列。"""
    sql_parts = []
    for table in TABLES:
        r = run_psql(
            f"SELECT column_name, pg_get_serial_sequence(table_name, column_name) "
            f"FROM information_schema.columns WHERE table_name='{table}' AND column_default LIKE 'nextval%%';"
        )
        for line in r.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 2 and parts[1]:
                col_name = parts[0]
                seq_name = parts[1]
                table_name = seq_name.split(".")[0].strip('"')
                sql_parts.append(
                    f"SELECT setval('{seq_name}', COALESCE((SELECT MAX({col_name}) FROM {table_name}), 1), true);"
                )
                print(f"  序列 {seq_name} 对齐")

    if sql_parts:
        run_psql_multi("\n".join(sql_parts))


def main():
    print("=" * 50)
    print("APT Mining — 旧库关系数据迁移到正式平台")
    print("=" * 50)
    print()

    if not os.path.exists(OLD_DB):
        print(f"错误: SQLite 文件不存在: {OLD_DB}")
        sys.exit(1)

    sqlite_conn = sqlite3.connect(OLD_DB)
    sqlite_cur = sqlite_conn.cursor()

    # 获取 PG 数据类型
    pg_types = {}
    for table in TABLES:
        pg_types[table] = get_pg_data_types(table)

    total = 0
    for table in TABLES:
        try:
            n = migrate_table(table, sqlite_cur, pg_types.get(table, {}))
            total += n
        except Exception as e:
            print(f"  {table}: FATAL 错误: {e}")

    print()
    print("对齐序列...")
    fix_sequences()

    sqlite_conn.close()

    print()
    print(f"迁移完成！共 {total} 条记录。")
    print("请重启正式后端 (python start.py --go) 使数据生效。")


if __name__ == "__main__":
    main()
