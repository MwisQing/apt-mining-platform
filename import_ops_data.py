#!/usr/bin/env python3
"""导入运营数据到 PostgreSQL 新平台（对应 export_ops_data.py 导出的 JSON）。

用法：
    python import_ops_data.py ops-export.json           # 导入正式库
    python import_ops_data.py ops-export.json --test    # 导入测试库
"""
import json
import subprocess
import sys
import os
from pathlib import Path

PG_HOST = "127.0.0.1"
PG_PORT = 5432
PG_USER = "postgres"
PG_PASS = "562245610"  # 改成你的 postgres 密码
PG_PROD_DB = "apt_mining_prod"
PG_TEST_DB = "apt_mining_test"
PG_BIN = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"

TABLES = [
    "mined_events", "mined_event_devices", "mined_event_iocs",
    "event_followups", "traced_targets", "tags", "tag_batches",
    "device_tags", "imports", "import_sheets", "config_data",
]


def run_psql(db, sql):
    env = os.environ.copy()
    env["PGPASSWORD"] = PG_PASS
    return subprocess.run(
        [PG_BIN, "-h", PG_HOST, "-U", PG_USER, "-d", db, "-c", sql],
        env=env, capture_output=True, text=True,
    )


def run_psql_multi(db, sql_text):
    env = os.environ.copy()
    env["PGPASSWORD"] = PG_PASS
    return subprocess.run(
        [PG_BIN, "-h", PG_HOST, "-U", PG_USER, "-d", db],
        env=env, input=sql_text, capture_output=True, text=True,
    )


def get_pg_columns(db, table):
    r = run_psql(db, (
        f"SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema='public' AND table_name='{table}' "
        f"AND is_identity='NO' ORDER BY ordinal_position;"
    ))
    return [line.strip() for line in r.stdout.strip().split("\n")
            if line.strip() and line.strip() != "column_name"]


def get_pg_data_types(db, table):
    r = run_psql(db, (
        f"SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_schema='public' AND table_name='{table}' ORDER BY ordinal_position;"
    ))
    types = {}
    for line in r.stdout.strip().split("\n"):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 2:
            types[parts[0]] = parts[1]
    return types


def import_table(db, table, rows, pg_types):
    if not rows:
        print(f"  {table}: 无数据，跳过")
        return 0, 0

    pg_cols = get_pg_columns(db, table)
    if not pg_cols:
        print(f"  {table}: 表不存在或无列，跳过")
        return 0, 0

    json_keys = list(rows[0].keys())
    common_cols = [c for c in json_keys if c in pg_cols]
    if not common_cols:
        print(f"  {table}: 无共有列，跳过")
        return 0, 0

    pg_col_list = ", ".join(f'"{c}"' for c in common_cols)
    values_batch = []
    inserted = 0
    skipped = 0

    for row in rows:
        vals = []
        for col in common_cols:
            val = row.get(col)
            dtype = pg_types.get(col, "text")
            if val is None:
                vals.append("NULL")
            elif isinstance(val, bool):
                vals.append("TRUE" if val else "FALSE")
            elif isinstance(val, (int, float)):
                vals.append(str(int(val)) if dtype in ("integer", "bigint", "smallint") else str(val))
            else:
                vals.append(f"'{str(val).replace(chr(39), chr(39)+chr(39))}'")
        values_batch.append("(" + ", ".join(vals) + ")")

        if len(values_batch) >= 500:
            sql = f"INSERT INTO {table} ({pg_col_list}) VALUES {', '.join(values_batch)} ON CONFLICT DO NOTHING;"
            r = run_psql_multi(db, sql)
            if r.returncode == 0:
                inserted += len(values_batch)
            else:
                for vv in values_batch:
                    r1 = run_psql(db, f"INSERT INTO {table} ({pg_col_list}) VALUES {vv} ON CONFLICT DO NOTHING;")
                    if r1.returncode == 0:
                        inserted += 1
                    else:
                        skipped += 1
            values_batch = []

    if values_batch:
        sql = f"INSERT INTO {table} ({pg_col_list}) VALUES {', '.join(values_batch)} ON CONFLICT DO NOTHING;"
        r = run_psql_multi(db, sql)
        if r.returncode == 0:
            inserted += len(values_batch)
        else:
            for vv in values_batch:
                r1 = run_psql(db, f"INSERT INTO {table} ({pg_col_list}) VALUES {vv} ON CONFLICT DO NOTHING;")
                if r1.returncode == 0:
                    inserted += 1
                else:
                    skipped += 1

    print(f"  {table}: 成功 {inserted}, 跳过 {skipped} (共 {len(rows)} 条)")
    return inserted, skipped


def fix_sequences(db):
    for table in TABLES:
        r = run_psql(db, (
            f"SELECT column_name, pg_get_serial_sequence(table_name, column_name) "
            f"FROM information_schema.columns WHERE table_name='{table}' "
            f"AND column_default LIKE 'nextval%%';"
        ))
        sql_parts = []
        for line in r.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 2 and parts[1]:
                col_name, seq_name = parts
                tbl = seq_name.split(".")[0].strip('"')
                sql_parts.append(
                    f"SELECT setval('{seq_name}', "
                    f"COALESCE((SELECT MAX({col_name}) FROM {tbl}), 1), true);"
                )
        if sql_parts:
            run_psql_multi(db, "\n".join(sql_parts))


def main():
    db = PG_PROD_DB
    input_file = None

    i = 0
    args = sys.argv[1:]
    while i < len(args):
        if args[i] == "--test":
            db = PG_TEST_DB
            i += 1
        elif args[i] in ("--help", "-h"):
            print(__doc__)
            sys.exit(0)
        else:
            input_file = args[i]
            i += 1

    if not input_file:
        print("用法: python import_ops_data.py <json文件> [--test]")
        sys.exit(1)

    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    tables_data = data.get("tables", {})
    pg_types_cache = {t: get_pg_data_types(db, t) for t in TABLES}

    print("=" * 50)
    print(f"APT Mining — 导入运营数据到 {db}")
    print(f"源文件: {input_file}")
    print("=" * 50)
    print()

    total_ins, total_skip = 0, 0
    for table in TABLES:
        if table not in tables_data:
            continue
        ins, skip = import_table(db, table, tables_data[table], pg_types_cache.get(table, {}))
        total_ins += ins
        total_skip += skip

    print()
    print("对齐序列...")
    fix_sequences(db)

    print()
    print(f"导入完成！成功 {total_ins}, 跳过 {total_skip}")
    print(f"请重启后端 (python start.py --go) 使数据生效。")


if __name__ == "__main__":
    main()
