#!/usr/bin/env python3
"""导入运营数据到 PostgreSQL 新平台（对应 export_ops_data.py 导出的 JSON）。

用法：
    python import_ops_data.py ops-export.json           # 导入正式库
    python import_ops_data.py ops-export.json --test    # 导入测试库
"""
import json
import sys
import os

import psycopg2

PG_HOST = "127.0.0.1"
PG_PORT = 5432
PG_USER_PROD = "apt_prod"
PG_USER_TEST = "apt_test"
PG_PASS_PROD = "AptProd2026mining"  # 正式库密码
PG_PASS_TEST = "AptTest2026mining"  # 测试库密码
PG_PROD_DB = "apt_mining_prod"
PG_TEST_DB = "apt_mining_test"

# 导入顺序：无依赖表先导入，依赖表后导入（满足外键约束）
TABLES = [
    "mined_events",
    "tag_batches",
    "traced_targets",
    "imports",
    "mined_event_devices",
    "mined_event_iocs",
    "event_followups",
    "tags",
    "device_tags",
    "import_sheets",
]


def get_connection(db, user, password):
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        dbname=db, user=user, password=password,
    )


def get_pg_columns(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s "
            "AND is_identity='NO' ORDER BY ordinal_position",
            (table,)
        )
        return [row[0] for row in cur.fetchall()]


def get_pg_data_types(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
            (table,)
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def convert_value(val, dtype):
    """将 JSON 值转为适合 psycopg2 的 Python 对象。"""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if dtype in ("integer", "bigint", "smallint"):
            return int(val)
        return val
    return str(val)


def import_table(conn, table, rows, pg_types):
    if not rows:
        print(f"  {table}: 无数据，跳过")
        return 0, 0

    pg_cols = get_pg_columns(conn, table)
    if not pg_cols:
        print(f"  {table}: 表不存在或无列，跳过")
        return 0, 0

    json_keys = list(rows[0].keys())
    common_cols = [c for c in json_keys if c in pg_cols]
    if not common_cols:
        print(f"  {table}: 无共有列，跳过")
        return 0, 0

    col_placeholders = ", ".join(f'"{c}"' for c in common_cols)
    value_placeholders = ", ".join(["%s"] * len(common_cols))
    sql = (
        f"INSERT INTO {table} ({col_placeholders}) "
        f"VALUES ({value_placeholders}) ON CONFLICT DO NOTHING"
    )

    inserted = 0
    skipped = 0
    batch = []

    for row in rows:
        vals = tuple(
            convert_value(row.get(col), pg_types.get(col, "text"))
            for col in common_cols
        )
        batch.append(vals)

        if len(batch) >= 500:
            try:
                with conn.cursor() as cur:
                    cur.executemany(sql, batch)
                conn.commit()
                inserted += len(batch)
            except Exception as e:
                conn.rollback()
                # 逐行重试
                for vv in batch:
                    try:
                        with conn.cursor() as cur:
                            cur.execute(sql, vv)
                        conn.commit()
                        inserted += 1
                    except Exception:
                        conn.rollback()
                        skipped += 1
            batch = []

    if batch:
        try:
            with conn.cursor() as cur:
                cur.executemany(sql, batch)
            conn.commit()
            inserted += len(batch)
        except Exception as e:
            conn.rollback()
            for vv in batch:
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql, vv)
                    conn.commit()
                    inserted += 1
                except Exception:
                    conn.rollback()
                    skipped += 1

    print(f"  {table}: 成功 {inserted}, 跳过 {skipped} (共 {len(rows)} 条)")
    return inserted, skipped


def fix_sequences(conn):
    with conn.cursor() as cur:
        for table in TABLES:
            cur.execute(
                "SELECT column_name, pg_get_serial_sequence(table_name, column_name) "
                "FROM information_schema.columns WHERE table_name=%s "
                "AND column_default LIKE 'nextval%%'",
                (table,)
            )
            for col_name, seq_name in cur.fetchall():
                if seq_name:
                    cur.execute(
                        f"SELECT setval(%s, COALESCE((SELECT MAX({col_name}) "
                        f"FROM {table}), 1), true)",
                        (seq_name,)
                    )
    conn.commit()


def main():
    db = PG_PROD_DB
    user = PG_USER_PROD
    password = PG_PASS_PROD
    input_file = None

    i = 0
    args = sys.argv[1:]
    while i < len(args):
        if args[i] == "--test":
            db = PG_TEST_DB
            user = PG_USER_TEST
            password = PG_PASS_TEST
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

    print("=" * 50)
    print(f"APT Mining — 导入运营数据到 {db}")
    print(f"源文件: {input_file}")
    print("=" * 50)
    print()

    conn = get_connection(db, user, password)
    try:
        pg_types_cache = {}
        for t in TABLES:
            pg_types_cache[t] = get_pg_data_types(conn, t)

        total_ins, total_skip = 0, 0
        for table in TABLES:
            if table not in tables_data:
                continue
            ins, skip = import_table(
                conn, table, tables_data[table], pg_types_cache.get(table, {})
            )
            total_ins += ins
            total_skip += skip

        print()
        print("对齐序列...")
        fix_sequences(conn)
    finally:
        conn.close()

    print()
    print(f"导入完成！成功 {total_ins}, 跳过 {total_skip}")
    print(f"请重启后端使数据生效。")


if __name__ == "__main__":
    main()
