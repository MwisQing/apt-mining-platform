"""
从 v0.7 的存量数据一次性导入：
  - 01.排查成功的设备id.txt -> 永久标签 "排查成功"
  - 02.重点设备id.txt -> 永久标签 "重点设备"
  - 03.不好查设备id.txt -> 永久标签 "不好排查"
  - 04.追踪过的外联目标.xlsx -> 追踪库
运行方式: python -m backend.scripts.import_v07_data
"""
import os
import sys
import re
from datetime import datetime
from sqlalchemy import text

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from backend.utils.db import init_db, get_session_local
from backend.utils import get_path


def read_txt_ids(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def parse_date_from_note(note):
    if not note:
        return None
    patterns = [
        (r"(\d{4})年(\d{1,2})月(\d{1,2})日", lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"),
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"),
        (r"(\d{4})\.(\d{1,2})\.(\d{1,2})", lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"),
        (r"(\d{1,2})/(\d{1,2})", lambda m: f"2026-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),
    ]
    for pattern, formatter in patterns:
        match = re.search(pattern, note)
        if match:
            return formatter(match)
    return None


def import_device_tags(db, base_dir):
    tag_map = {
        "01.排查成功的设备id.txt": ("排查成功", "#67C23A"),
        "02.重点设备id.txt": ("重点设备", "#F56C6C"),
        "03.不好查设备id.txt": ("不好排查", "#909399"),
    }

    now = datetime.now().isoformat()
    total = 0

    for filename, (tag_name, color) in tag_map.items():
        filepath = os.path.join(base_dir, filename)
        ids = read_txt_ids(filepath)
        if not ids:
            print(f"  跳过 {filename} (文件不存在或为空)")
            continue

        # Ensure permanent tag exists
        row = db.execute(
            text("SELECT id FROM tags WHERE name = :name AND is_permanent = 1"),
            {"name": tag_name}
        ).fetchone()
        if row:
            tag_id = row[0]
        else:
            cursor = db.execute(
                text(
                    "INSERT INTO tags (name, color, is_permanent, batch_id, created_at) "
                    "VALUES (:name, :color, 1, NULL, :created_at)"
                ),
                {"name": tag_name, "color": color, "created_at": now}
            )
            tag_id = cursor.lastrowid

        for device_id in ids:
            db.execute(
                text(
                    "INSERT OR IGNORE INTO device_tags (device_id, tag_id, created_at) "
                    "VALUES (:did, :tid, :created_at)"
                ),
                {"did": device_id, "tid": tag_id, "created_at": now}
            )
            total += 1

        print(f"  {filename}: {len(ids)} 个设备 -> 标签 '{tag_name}'")

    print(f"设备标签导入完成: 共 {total} 条")


def import_traced_targets(db, base_dir):
    import pandas as pd

    filepath = os.path.join(base_dir, "04.追踪过的外联目标.xlsx")
    if not os.path.exists(filepath):
        print("  跳过 04.追踪过的外联目标.xlsx (文件不存在)")
        return

    df = pd.read_excel(filepath)
    now = datetime.now().isoformat()
    count = 0

    for _, row in df.iterrows():
        target = str(row.get("外联目标", row.get("target", ""))).strip()
        port = str(row.get("外联端口", row.get("port", ""))).strip() if pd.notna(row.get("外联端口", row.get("port"))) else None
        if not port or port == "nan":
            port = None
        note = str(row.get("备注", row.get("note", ""))).strip() if pd.notna(row.get("备注", row.get("note"))) else ""

        traced_at = parse_date_from_note(note) or now

        cursor = db.execute(
            text(
                "INSERT OR IGNORE INTO traced_targets (target, port, traced_at, note) "
                "VALUES (:target, :port, :traced_at, :note)"
            ),
            {"target": target, "port": port, "traced_at": traced_at, "note": note}
        )
        if cursor.lastrowid:
            count += 1

    print(f"追踪库导入完成: 新增 {count} 条")


def main():
    print("=== v0.7 存量数据导入 ===")
    init_db()
    db = get_session_local()()

    # Find v0.7 data files (in project root)
    base_dir = project_root

    print("导入设备标签...")
    import_device_tags(db, base_dir)

    print("导入追踪库...")
    import_traced_targets(db, base_dir)

    db.commit()
    db.close()
    print("=== 导入完成 ===")


if __name__ == "__main__":
    main()
