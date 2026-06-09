#!/usr/bin/env python3
"""Export Go/PostgreSQL operational data to a JSON migration package.

Exports only operator-created state: tags, events, IOC notes, and event followups.
Excludes: full alerts, import history, audit log, alert annotations, config,
uploaded files, and Excel source rows.

Usage:
    python export_ops_data_go.py
    python export_ops_data_go.py --output ops-export-go.json
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as e:
    print(f"Error: psycopg2 is required but not installed. ({e})")
    print("Install it with: pip install psycopg2-binary")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent

EXPORT_TABLES = [
    "tag_batches",
    "tags",
    "device_tags",
    "traced_targets",
    "mined_events",
    "mined_event_devices",
    "mined_event_iocs",
    "event_followups",
]

TABLE_DESCRIPTIONS = {
    "tag_batches": "tag batches",
    "tags": "tags",
    "device_tags": "device tag links",
    "traced_targets": "IOC notes and trace records",
    "mined_events": "events",
    "mined_event_devices": "event device links",
    "mined_event_iocs": "event IOC links",
    "event_followups": "event followups",
}


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


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def table_exists(conn, table):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = %s
            )
            """,
            (table,),
        )
        return bool(cur.fetchone()[0])


def export_table(conn, table):
    if not table_exists(conn, table):
        print(f"  {table}: skipped, table does not exist")
        return []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f'SELECT * FROM "{table}" ORDER BY 1')
        return [dict(row) for row in cur.fetchall()]



def build_package(conn):
    package = {
        "format": "apt-mining-go-ops-export",
        "version": 1,
        "exported_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "source": {
            "db_name": os.environ.get("APT_DB_NAME", "apt_mining_test"),
            "excluded": ["full alerts", "import_rows", "uploaded Excel files", "import history", "audit log", "alert annotations", "config"],
        },
        "tables": {},
    }
    for table in EXPORT_TABLES:
        rows = export_table(conn, table)
        package["tables"][table] = rows
        desc = TABLE_DESCRIPTIONS.get(table, table)
        print(f"  {desc} ({table}): {len(rows)} rows")
    return package


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="ops-export-go.json")
    parser.add_argument("--env", help="Path to .env file. Defaults to project .env.")
    return parser.parse_args()


def main():
    args = parse_args()
    load_dotenv(args.env)

    print("=" * 60)
    print("APT Mining - export Go/PostgreSQL operational data")
    print(f"Database: {os.environ.get('APT_DB_NAME', 'apt_mining_test')}")
    print("=" * 60)

    conn = get_connection()
    try:
        package = build_package(conn)
    finally:
        conn.close()

    output = Path(args.output)
    with output.open("w", encoding="utf-8") as f:
        json.dump(package, f, ensure_ascii=False, indent=2, default=json_default)

    size_kb = output.stat().st_size / 1024
    print()
    print(f"Export complete: {output} ({size_kb:.1f} KB)")
    print("Copy this JSON to the new machine and run import_ops_data_go.py.")


if __name__ == "__main__":
    main()
