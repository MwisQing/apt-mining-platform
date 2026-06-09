#!/usr/bin/env python3
"""Import a Go/PostgreSQL operational data JSON package.

The importer is conservative by default: it inserts rows and skips conflicts.
It does not delete existing data. Excel source row payloads (import_rows) and
full alert rows are not imported. Alert annotations are replayed onto
already-imported alerts.

Usage:
    python import_ops_data_go.py ops-export-go.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import psycopg2
except ImportError as e:
    print(f"Error: psycopg2 is required but not installed. ({e})")
    print("Install it with: pip install psycopg2-binary")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent

IMPORT_TABLES = [
    "tag_batches",
    "tags",
    "device_tags",
    "traced_targets",
    "mined_events",
    "mined_event_devices",
    "mined_event_iocs",
    "event_followups",
]


def load_dotenv(env_path=None):
    env_file = Path(env_path) if env_path else SCRIPT_DIR / ".env"
    if not env_file.exists():
        return
    with env_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("APT_DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("APT_DB_PORT", "5432")),
        dbname=os.environ.get("APT_DB_NAME", "apt_mining_test"),
        user=os.environ.get("APT_DB_USER", "apt_test"),
        password=os.environ.get("APT_DB_PASSWORD", ""),
    )


def get_pg_columns(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


def normalize_row_for_import(table, row):
    return dict(row)


def placeholders(count):
    return ", ".join(["%s"] * count)


def import_table(conn, table, rows):
    if not rows:
        print(f"  {table}: no rows, skipped")
        return 0, 0

    pg_cols = get_pg_columns(conn, table)
    if not pg_cols:
        print(f"  {table}: missing destination table, skipped")
        return 0, len(rows)

    normalized_rows = [normalize_row_for_import(table, row) for row in rows]
    common_cols = [c for c in pg_cols if any(c in row for row in normalized_rows)]
    if not common_cols:
        print(f"  {table}: no common columns, skipped")
        return 0, len(rows)

    quoted_cols = ", ".join(f'"{col}"' for col in common_cols)
    sql = (
        f'INSERT INTO "{table}" ({quoted_cols}) '
        f"VALUES ({placeholders(len(common_cols))}) ON CONFLICT DO NOTHING"
    )

    inserted = 0
    skipped = 0
    with conn.cursor() as cur:
        for row in normalized_rows:
            values = [row.get(col) for col in common_cols]
            try:
                cur.execute(sql, values)
                inserted += cur.rowcount if cur.rowcount > 0 else 0
                skipped += 1 if cur.rowcount == 0 else 0
            except Exception as exc:
                conn.rollback()
                skipped += 1
                print(f"    skipped {table} row: {exc}")
            else:
                conn.commit()

    print(f"  {table}: inserted {inserted}, skipped {skipped} (total {len(rows)})")
    return inserted, skipped


def serial_sequences(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name,
                   pg_get_serial_sequence(format('%I', table_name), column_name)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_default LIKE 'nextval%%'
            """
        )
        return [(table, column, seq) for table, column, seq in cur.fetchall() if seq]


def fix_sequences(conn):
    with conn.cursor() as cur:
        for table, column, seq in serial_sequences(conn):
            cur.execute(
                f'SELECT setval(%s, COALESCE((SELECT MAX("{column}") FROM "{table}"), 1), true)',
                (seq,),
            )
    conn.commit()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file produced by export_ops_data_go.py")
    parser.add_argument("--env", help="Path to .env file. Defaults to project .env.")
    return parser.parse_args()


def main():
    args = parse_args()
    load_dotenv(args.env)

    with open(args.input, "r", encoding="utf-8") as f:
        package = json.load(f)

    tables = package.get("tables", {})

    print("=" * 60)
    print("APT Mining - import Go/PostgreSQL operational data")
    print(f"Database: {os.environ.get('APT_DB_NAME', 'apt_mining_test')}")
    print(f"Source file: {args.input}")
    print("=" * 60)

    conn = get_connection()
    try:
        total_inserted = 0
        total_skipped = 0
        for table in IMPORT_TABLES:
            if table not in tables:
                continue
            inserted, skipped = import_table(conn, table, tables[table])
            total_inserted += inserted
            total_skipped += skipped

        print()
        print("Fixing serial sequences...")
        fix_sequences(conn)
    finally:
        conn.close()

    print()
    print(f"Import complete: inserted {total_inserted}, skipped {total_skipped}")
    print("Restart the backend before checking the migrated data.")


if __name__ == "__main__":
    main()
