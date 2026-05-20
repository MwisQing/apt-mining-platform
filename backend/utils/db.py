from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
import os
import json
from datetime import datetime
from backend.services.alert_workbench import compute_alert_content_hash

_engine = None
_SessionLocal = None


def get_engine(db_path=None):
    global _engine
    if _engine is None:
        if db_path is None:
            from backend.utils import get_path
            db_path = get_path("db")
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=3,
            pool_pre_ping=True,
            pool_timeout=10,
        )

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
    return _engine


def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def init_db():
    from backend.models import Base
    from backend.utils import get_path
    # Ensure data directory exists
    os.makedirs(os.path.dirname(get_path("db")), exist_ok=True)
    # Import all models so they register with Base.metadata
    from backend.models import alert, tag, traced_target, event, import_model, snapshot  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_runtime_schema(engine)


def _table_columns(connection, table_name):
    rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _add_column_if_missing(connection, table_name, column_name, ddl):
    if column_name not in _table_columns(connection, table_name):
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))


def _recreate_snapshot_tables(connection):
    connection.execute(text("DROP TABLE IF EXISTS alert_candidate_snapshot_badges"))
    connection.execute(text("DROP TABLE IF EXISTS alert_candidate_snapshot_tags"))
    connection.execute(text("DROP TABLE IF EXISTS alert_candidate_snapshots"))
    connection.execute(text(
        "UPDATE snapshot_build_meta SET "
        "active_version = NULL, building_version = NULL, status = 'idle', "
        "last_row_count = 0, last_error = NULL "
        "WHERE snapshot_type = 'alert_candidates'"
    ))


def _ensure_runtime_schema(engine):
    with engine.begin() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL"))

        for column_name in ("total_rows", "parsed_rows", "raw_rows"):
            _add_column_if_missing(connection, "imports", column_name, f"{column_name} INTEGER")
        _add_column_if_missing(connection, "imports", "file_hash", "file_hash TEXT")
        _add_column_if_missing(connection, "imports", "queue_position", "queue_position INTEGER")

        for column_name, ddl in {
            "import_id": "import_id INTEGER",
            "import_sheet_id": "import_sheet_id INTEGER",
            "import_row_id": "import_row_id INTEGER",
            "sheet_name": "sheet_name TEXT",
            "excel_row_number": "excel_row_number INTEGER",
            "raw_row_hash": "raw_row_hash TEXT",
            "content_hash": "content_hash TEXT",
        }.items():
            _add_column_if_missing(connection, "alerts", column_name, ddl)

        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_import_id ON alerts(import_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_import_row_id ON alerts(import_row_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_content_hash ON alerts(content_hash)"
        ))
        _add_column_if_missing(connection, "alerts", "analysis_status", "analysis_status TEXT DEFAULT ''")
        _add_column_if_missing(connection, "alerts", "is_focused", "is_focused INTEGER DEFAULT 0")
        _add_column_if_missing(connection, "alerts", "intel_position", "intel_position TEXT")
        _add_column_if_missing(connection, "alerts", "disposal_action", "disposal_action TEXT")
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_is_focused ON alerts(is_focused)"
        ))
        # Performance indexes for filtering and sorting with large datasets
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_first_alert_time ON alerts(first_alert_time)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_device_id ON alerts(device_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_target ON alerts(target)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_source_ip ON alerts(source_ip)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_threat_type ON alerts(threat_type)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_std_apt_org ON alerts(std_apt_org)"
        ))
        # Composite indexes for heat map and source_ip consolidation queries
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_alerts_heat_group ON alerts(device_id, target, source_ip)"
        ))
        # Index for traced_targets lookup (expired_revive badge, trace maps)
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_traced_target_port ON traced_targets(target, port)"
        ))
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS snapshot_build_meta ("
            "snapshot_type TEXT PRIMARY KEY, "
            "active_version TEXT, "
            "building_version TEXT, "
            "status TEXT NOT NULL DEFAULT 'idle', "
            "last_built_at TEXT, "
            "last_build_started_at TEXT, "
            "last_build_duration_ms INTEGER DEFAULT 0, "
            "last_row_count INTEGER DEFAULT 0, "
            "last_error TEXT)"
        ))
        # Clean orphaned building_version from crashed previous runs
        connection.execute(text(
            "UPDATE snapshot_build_meta SET "
            "building_version = NULL, status = 'idle' "
            "WHERE building_version IS NOT NULL"
        ))
        snapshot_columns = _table_columns(connection, "alert_candidate_snapshots")
        if snapshot_columns and "alert_id" not in snapshot_columns:
            _recreate_snapshot_tables(connection)
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS alert_candidate_snapshots ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "alert_id INTEGER, "
            "snapshot_version TEXT NOT NULL, "
            "device_id TEXT NOT NULL, "
            "target TEXT NOT NULL, "
            "port TEXT NOT NULL DEFAULT '', "
            "source_ip TEXT, "
            "source_ips TEXT, "
            "source_ip_count INTEGER DEFAULT 0, "
            "target_type TEXT, "
            "target_kind TEXT, "
            "target_kind_label TEXT, "
            "threat_type TEXT, "
            "threat_level TEXT, "
            "std_apt_org TEXT, "
            "apt_org TEXT, "
            "apt_org_tier TEXT, "
            "vendors TEXT, "
            "protocol TEXT, "
            "intel_tags TEXT, "
            "dns_resolved_ip TEXT, "
            "asset_type TEXT, "
            "analysis_status TEXT DEFAULT '', "
            "is_focused INTEGER DEFAULT 0, "
            "alert_count INTEGER DEFAULT 0, "
            "first_alert_time TEXT, "
            "last_alert_time TEXT, "
            "heat_target_alert_count INTEGER DEFAULT 0, "
            "heat_target_device_count INTEGER DEFAULT 0, "
            "heat_device_alert_count INTEGER DEFAULT 0, "
            "heat_device_target_count INTEGER DEFAULT 0, "
            "heat_source_ip_alert_count INTEGER DEFAULT 0, "
            "candidate_score INTEGER DEFAULT 0, "
            "candidate_priority TEXT, "
            "candidate_priority_label TEXT, "
            "candidate_rule_ids_json TEXT, "
            "candidate_reasons_json TEXT, "
            "event_json TEXT, "
            "event_status TEXT, "
            "trace_json TEXT, "
            "trace_status TEXT, "
            "ioc_note TEXT, "
            "cross_day INTEGER DEFAULT 0, "
            "lateral INTEGER DEFAULT 0, "
            "heat_summary_json TEXT, "
            "relation_summary TEXT, "
            "candidate_summary TEXT, "
            "candidate_focus TEXT, "
            "device_note_summary TEXT, "
            "sort_priority_rank INTEGER DEFAULT 0, "
            "sort_rule_hits INTEGER DEFAULT 0, "
            "sort_target_device_count INTEGER DEFAULT 0, "
            "sort_target_alert_count INTEGER DEFAULT 0, "
            "sort_source_ip_alert_count INTEGER DEFAULT 0, "
            "sort_trace_status TEXT, "
            "sort_event_status TEXT, "
            "updated_at TEXT NOT NULL, "
            "UNIQUE(snapshot_version, alert_id))"
        ))
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS alert_candidate_snapshot_badges ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "snapshot_version TEXT NOT NULL, "
            "snapshot_id INTEGER NOT NULL, "
            "badge_name TEXT NOT NULL, "
            "badge_label TEXT NOT NULL, "
            "badge_color TEXT, "
            "FOREIGN KEY(snapshot_id) REFERENCES alert_candidate_snapshots(id) ON DELETE CASCADE)"
        ))
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS alert_candidate_snapshot_tags ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "snapshot_version TEXT NOT NULL, "
            "snapshot_id INTEGER NOT NULL, "
            "tag_id INTEGER NOT NULL, "
            "tag_name TEXT NOT NULL, "
            "tag_color TEXT, "
            "FOREIGN KEY(snapshot_id) REFERENCES alert_candidate_snapshots(id) ON DELETE CASCADE)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_first_time "
            "ON alert_candidate_snapshots(snapshot_version, first_alert_time)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_score "
            "ON alert_candidate_snapshots(snapshot_version, candidate_score DESC)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_target_type "
            "ON alert_candidate_snapshots(snapshot_version, target_type)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_threat_type "
            "ON alert_candidate_snapshots(snapshot_version, threat_type)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_threat_level "
            "ON alert_candidate_snapshots(snapshot_version, threat_level)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_apt_tier "
            "ON alert_candidate_snapshots(snapshot_version, apt_org_tier)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_trace "
            "ON alert_candidate_snapshots(snapshot_version, trace_status)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_priority "
            "ON alert_candidate_snapshots(snapshot_version, candidate_priority)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_version_target "
            "ON alert_candidate_snapshots(snapshot_version, target)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_badges_version_name "
            "ON alert_candidate_snapshot_badges(snapshot_version, badge_name)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_badges_version_snapshot "
            "ON alert_candidate_snapshot_badges(snapshot_version, snapshot_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_tags_version_tag "
            "ON alert_candidate_snapshot_tags(snapshot_version, tag_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_tags_version_name "
            "ON alert_candidate_snapshot_tags(snapshot_version, tag_name)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_tags_version_snapshot "
            "ON alert_candidate_snapshot_tags(snapshot_version, snapshot_id)"
        ))
        # Precompute v3: new columns for pre-stored JSON data
        _add_column_if_missing(connection, "alert_candidate_snapshots", "alert_id", "alert_id INTEGER")
        _add_column_if_missing(connection, "alert_candidate_snapshots", "badges_json", "badges_json TEXT DEFAULT '[]'")
        _add_column_if_missing(connection, "alert_candidate_snapshots", "device_tags_json", "device_tags_json TEXT DEFAULT '[]'")
        _add_column_if_missing(connection, "alert_candidate_snapshots", "device_event_json", "device_event_json TEXT")
        # Precompute v3: performance indexes for incremental updates and queries
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_target_port "
            "ON alert_candidate_snapshots(snapshot_version, target, port)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_device_id "
            "ON alert_candidate_snapshots(snapshot_version, device_id)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_date_range "
            "ON alert_candidate_snapshots(snapshot_version, first_alert_time, last_alert_time)"
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_snap_score_desc "
            "ON alert_candidate_snapshots(snapshot_version, candidate_score DESC)"
        ))
        _add_column_if_missing(connection, "tag_batches", "status", "status TEXT DEFAULT 'active'")
        _add_column_if_missing(connection, "tag_batches", "device_ids_snapshot", "device_ids_snapshot TEXT")
        _dedupe_tags(connection)
        _backfill_alert_content_hashes(connection)
        _backfill_tag_batch_device_snapshots(connection)


def _dedupe_tags(connection):
    """Merge duplicate tags (same name, different ids) into one record, preferring permanent tags.
    Also normalizes trailing whitespace in tag names."""
    # Step 1: Trim trailing whitespace from all tag names
    connection.execute(text(
        "UPDATE tags SET name = RTRIM(name) WHERE name != RTRIM(name)"
    ))
    # Step 2: Merge exact duplicates after normalization
    dupes = connection.execute(text(
        "SELECT name, COUNT(*) AS cnt FROM tags GROUP BY name HAVING cnt > 1"
    )).fetchall()
    for name, _ in dupes:
        # Prefer permanent tags, then the oldest
        rows = connection.execute(text(
            "SELECT id, is_permanent FROM tags WHERE name = :name "
            "ORDER BY CASE WHEN is_permanent = 1 THEN 0 ELSE 1 END, id ASC"
        ), {"name": name}).fetchall()
        if len(rows) <= 1:
            continue
        keep_id = rows[0][0]
        for dup_row in rows[1:]:
            dup_id = dup_row[0]
            # Update device_tags one at a time to handle PK conflicts safely
            dt_rows = connection.execute(text(
                "SELECT device_id FROM device_tags WHERE tag_id = :dup_id"
            ), {"dup_id": dup_id}).fetchall()
            for (device_id,) in dt_rows:
                # Check if keep_id already exists for this device
                existing = connection.execute(text(
                    "SELECT 1 FROM device_tags WHERE device_id = :did AND tag_id = :tid"
                ), {"did": device_id, "tid": keep_id}).fetchone()
                if existing:
                    # Already has keep tag, just remove dup
                    connection.execute(text(
                        "DELETE FROM device_tags WHERE device_id = :did AND tag_id = :dup_id"
                    ), {"did": device_id, "dup_id": dup_id})
                else:
                    # Safe to update
                    connection.execute(text(
                        "UPDATE device_tags SET tag_id = :keep_id WHERE device_id = :did AND tag_id = :dup_id"
                    ), {"did": device_id, "keep_id": keep_id, "dup_id": dup_id})
            connection.execute(text(
                "DELETE FROM tags WHERE id = :dup_id"
            ), {"dup_id": dup_id})


def _backfill_alert_content_hashes(connection):
    rows = connection.execute(text(
        """
        SELECT
            id,
            device_id,
            first_alert_time,
            last_alert_time,
            source_ip,
            target,
            target_type,
            port,
            threat_type,
            threat_level,
            std_apt_org,
            apt_org,
            apt_org_tier,
            alert_count,
            vendors,
            protocol,
            intel_tags,
            dns_resolved_ip,
            down_traffic,
            up_traffic,
            asset_type
        FROM alerts
        WHERE content_hash IS NULL OR content_hash = ''
        """
    )).fetchall()

    for row in rows:
        row_map = dict(row._mapping)
        alert_id = row_map.pop("id")
        content_hash = compute_alert_content_hash(row_map)
        connection.execute(text(
            "UPDATE alerts SET content_hash = :content_hash WHERE id = :id"
        ), {"id": alert_id, "content_hash": content_hash})


def _backfill_tag_batch_device_snapshots(connection):
    rows = connection.execute(text(
        """
        SELECT id
        FROM tag_batches
        WHERE device_ids_snapshot IS NULL OR TRIM(device_ids_snapshot) = ''
        """
    )).fetchall()

    for (batch_id,) in rows:
        device_rows = connection.execute(text(
            """
            SELECT DISTINCT dt.device_id
            FROM device_tags dt
            JOIN tags t ON t.id = dt.tag_id
            WHERE t.batch_id = :batch_id
            ORDER BY dt.device_id
            """
        ), {"batch_id": batch_id}).fetchall()
        device_ids = [row[0] for row in device_rows if row[0]]
        if not device_ids:
            continue
        connection.execute(text(
            "UPDATE tag_batches SET device_ids_snapshot = :snapshot WHERE id = :id"
        ), {"id": batch_id, "snapshot": json.dumps(device_ids, ensure_ascii=False)})


def get_db():
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def write_audit(db, action, target_type=None, target_id=None, detail=None):
    if detail is not None and not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)
    db.execute(text(
        "INSERT INTO audit_log (action, target_type, target_id, detail, created_at) "
        "VALUES (:action, :target_type, :target_id, :detail, :created_at)"
    ), {
        "action": action,
        "target_type": target_type,
        "target_id": str(target_id) if target_id is not None else None,
        "detail": detail,
        "created_at": datetime.now().isoformat(),
    })
