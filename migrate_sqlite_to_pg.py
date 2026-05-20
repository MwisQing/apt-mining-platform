#!/usr/bin/env python3
"""SQLite to PostgreSQL data migration for APT Mining Platform v4.0 (Go rewrite).

Usage:
  python migrate_sqlite_to_pg.py --sqlite ./data/workbench.db --pg-db apt_mining_prod
  python migrate_sqlite_to_pg.py --sqlite ./data/workbench-test.db --pg-db apt_mining_test --backup

Tables are migrated in dependency order (tags first, then device_tags, etc.).
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

# Tables in dependency order (parent before child)
TABLES = [
    "tags",
    "tag_batches",
    "device_tags",
    "traced_targets",
    "mined_events",
    "mined_event_devices",
    "mined_event_iocs",
    "event_followups",
    "alerts",
    "imports",
    "import_sheets",
    "import_rows",
    "audit_log",
]


def parse_args():
    p = argparse.ArgumentParser(description="SQLite -> PostgreSQL migration")
    p.add_argument("--sqlite", required=True, help="Path to SQLite database")
    p.add_argument("--pg-host", default="127.0.0.1")
    p.add_argument("--pg-port", default="5432")
    p.add_argument("--pg-db", required=True, help="PostgreSQL database name")
    p.add_argument("--pg-user", default="postgres")
    p.add_argument("--pg-password", default="")
    p.add_argument("--backup", action="store_true", help="Backup SQLite before migration")
    return p.parse_args()


def backup_sqlite(path: str):
    if not os.path.exists(path):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = f"{path}.backup.{ts}"
    shutil.copy2(path, dest)
    print(f"  SQLite backup: {dest}")


def get_sqlite_columns(cur: sqlite3.Cursor, table: str) -> list:
    """Get column names for a table, excluding SQLite internal columns."""
    cur.execute(f"PRAGMA table_info({table})")
    skip = {"rowid"}
    return [row[1] for row in cur.fetchall() if row[1] not in skip]


def migrate_table(table: str, sqlite_conn: sqlite3.Connection, pg_conn) -> int:
    """Migrate a single table from SQLite to PostgreSQL."""
    cur = sqlite_conn.cursor()
    columns = get_sqlite_columns(cur, table)
    if not columns:
        print(f"  {table}: no columns, skip")
        return 0

    cur.execute(f"SELECT {', '.join(columns)} FROM {table}")
    rows = cur.fetchall()
    if not rows:
        print(f"  {table}: empty, skip")
        return 0

    pg_cur = pg_conn.cursor()
    col_list = ", ".join(columns)
    placeholders = ", ".join([f"%({c})s" for c in columns])
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    count = 0
    for row in rows:
        d = {}
        for i, col in enumerate(columns):
            val = row[i]
            if isinstance(val, str):
                d[col] = val
            elif val is None:
                d[col] = None
            else:
                d[col] = val
        try:
            pg_cur.execute(sql, d)
            count += 1
        except Exception as e:
            # Print first few errors, then suppress
            if count < 3:
                print(f"    [{table}] row insert warning: {e}")

    pg_conn.commit()
    print(f"  {table}: {count}/{len(rows)} rows")
    return count


def main():
    args = parse_args()

    if not os.path.exists(args.sqlite):
        print(f"ERROR: SQLite database not found: {args.sqlite}")
        sys.exit(1)

    if args.backup:
        backup_sqlite(args.sqlite)

    print(f"Connecting SQLite: {args.sqlite}")
    sqlite_conn = sqlite3.connect(args.sqlite)

    print(f"Connecting PostgreSQL: {args.pg_host}:{args.pg_port}/{args.pg_db}")
    pg_conn = psycopg2.connect(
        host=args.pg_host,
        port=args.pg_port,
        dbname=args.pg_db,
        user=args.pg_user,
        password=args.pg_password,
    )

    failed_tables = []
    total = 0
    for table in TABLES:
        try:
            count = migrate_table(table, sqlite_conn, pg_conn)
            total += count
        except Exception as e:
            print(f"  {table}: FATAL error: {e}")
            failed_tables.append(table)

    # Fix 6: Align PostgreSQL sequences to prevent duplicate key on next insert.
    # After inserting rows with explicit IDs, sequences must be set to MAX(id).
    pg_cur = pg_conn.cursor()
    for table in TABLES:
        try:
            pg_cur.execute(
                "SELECT column_name, pg_get_serial_sequence(table_name, column_name) as seq_name "
                "FROM information_schema.columns "
                "WHERE table_name = %s AND column_default LIKE 'nextval%%'",
                (table,),
            )
            for col_name, seq_name in pg_cur.fetchall():
                if not seq_name:
                    continue
                pg_cur.execute(f"SELECT COALESCE(MAX({col_name}), 1) FROM {table}")
                max_id = pg_cur.fetchone()[0]
                pg_cur.execute(f"SELECT setval(%s, %s, true)", (seq_name, max_id))
                print(f"  {table}.{col_name} sequence set to {max_id}")
        except Exception as e:
            print(f"  {table} sequence fix warning: {e}")
    pg_conn.commit()

    sqlite_conn.close()
    pg_conn.close()

    if failed_tables:
        print(f"\nMigration completed with ERRORS in: {', '.join(failed_tables)}")
        print("These tables were NOT migrated successfully.")
        sys.exit(1)
    else:
        print(f"\nMigration complete! {total} total rows across {len(TABLES)} tables.")


if __name__ == "__main__":
    main()
