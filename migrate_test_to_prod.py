#!/usr/bin/env python3
"""将测试平台的关系数据（事件/标签/追踪）迁移到正式平台。

不迁移告警数据，只迁移：
- mined_events + mined_event_devices + mined_event_iocs + event_followups
- tags + tag_batches + device_tags
- traced_targets
"""
import psycopg2
from psycopg2.extras import execute_values

PROD_DB = "apt_mining_prod"
TEST_DB = "apt_mining_test"
PG_HOST = "127.0.0.1"
PG_USER = "postgres"
PG_PASS = "562245610"  # 改成你的 postgres 密码

# 需要迁移的表（按依赖顺序）
TABLES = [
    "tag_batches",
    "tags",
    "device_tags",
    "traced_targets",
    "mined_events",
    "mined_event_devices",
    "mined_event_iocs",
    "event_followups",
]


def get_conn(dbname):
    return psycopg2.connect(
        host=PG_HOST, dbname=dbname, user=PG_USER, password=PG_PASS
    )


def migrate_table(table, src_cur, dst_cur):
    """迁移单表数据，遇到冲突则跳过。"""
    # 获取列名
    src_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (table,),
    )
    cols = [r[0] for r in src_cur.fetchall()]
    if not cols:
        print(f"  {table}: 无列，跳过")
        return 0

    # 查询源数据
    src_cur.execute(f"SELECT * FROM {table}")
    rows = src_cur.fetchall()
    if not rows:
        print(f"  {table}: 空表，跳过")
        return 0

    # 批量插入（ON CONFLICT DO NOTHING 跳过已存在的）
    col_list = ", ".join(cols)
    placeholders = ", ".join([f"%({c})s" for c in cols])
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    count = 0
    for row in rows:
        d = dict(zip(cols, row))
        # 处理 serial 字段：让 PG 自动生成 ID（跳过 id 列）
        if "id" in d:
            del d["id"]
            # 重新构造 SQL，排除 id 列
            real_cols = [c for c in cols if c != "id"]
            real_placeholders = ", ".join([f"%({c})s" for c in real_cols])
            real_col_list = ", ".join(real_cols)
            sql = f"INSERT INTO {table} ({real_col_list}) VALUES ({real_placeholders}) ON CONFLICT DO NOTHING"
            d_filtered = {k: v for k, v in d.items() if k != "id"}
        else:
            d_filtered = d

        try:
            dst_cur.execute(sql, d_filtered)
            count += 1
        except Exception as e:
            if count < 3:
                print(f"    [{table}] 插入警告: {e}")

    dst_cur.connection.commit()
    print(f"  {table}: 迁移 {count}/{len(rows)} 条")
    return count


def main():
    print("=" * 50)
    print("APT Mining — 测试数据迁移到正式平台")
    print("=" * 50)
    print()

    test_conn = get_conn(TEST_DB)
    prod_conn = get_conn(PROD_DB)
    test_cur = test_conn.cursor()
    prod_cur = prod_conn.cursor()

    total = 0
    for table in TABLES:
        try:
            count = migrate_table(table, test_cur, prod_cur)
            total += count
        except Exception as e:
            print(f"  {table}: FATAL 错误: {e}")

    # 对齐序列
    prod_cur.execute(
        "SELECT column_name, pg_get_serial_sequence(table_name, column_name) as seq_name "
        "FROM information_schema.columns WHERE table_schema='public' "
        "AND column_default LIKE 'nextval%%'"
    )
    for col_name, seq_name in prod_cur.fetchall():
        if not seq_name:
            continue
        table_name = seq_name.split(".")[0].strip('"')
        prod_cur.execute(f"SELECT COALESCE(MAX({col_name}), 1) FROM {table_name}")
        max_id = prod_cur.fetchone()[0]
        prod_cur.execute("SELECT setval(%s, %s, true)", (seq_name, max_id))
        print(f"  序列 {seq_name} 对齐到 {max_id}")
    prod_conn.commit()

    test_conn.close()
    prod_conn.close()

    print()
    print(f"迁移完成！共 {total} 条记录。")
    print("请重启正式后端 (python start.py --go) 使数据生效。")


if __name__ == "__main__":
    main()
