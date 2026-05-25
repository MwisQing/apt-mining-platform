-- APT Mining Platform v2.0 数据库迁移（PostgreSQL）
-- 基于 Python v3.x 的 SQLAlchemy schema，去除快照表

-- ====== 基础表（无外键） ======

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    device_id TEXT NOT NULL,
    first_alert_time TIMESTAMP NOT NULL,
    last_alert_time TIMESTAMP NOT NULL,
    source_ip TEXT NOT NULL,
    target TEXT NOT NULL,
    target_type TEXT,
    port TEXT,
    threat_type TEXT,
    threat_level TEXT,
    std_apt_org TEXT,
    apt_org TEXT,
    apt_org_tier TEXT,
    alert_count INTEGER,
    vendors TEXT,
    protocol TEXT,
    intel_tags TEXT,
    intel_position TEXT,
    disposal_action TEXT,
    dns_resolved_ip TEXT,
    down_traffic INTEGER,
    up_traffic INTEGER,
    asset_type TEXT,
    source_file TEXT NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    unique_hash TEXT,
    content_hash TEXT,
    import_id INTEGER,
    import_sheet_id INTEGER,
    import_row_id INTEGER,
    sheet_name TEXT,
    excel_row_number INTEGER,
    raw_row_hash TEXT,
    analysis_status TEXT DEFAULT '',
    is_focused INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mined_events (
    id SERIAL PRIMARY KEY,
    event_name TEXT NOT NULL,
    color TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    mined_at TIMESTAMP NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS tag_batches (
    id SERIAL PRIMARY KEY,
    batch_name TEXT,
    created_at TIMESTAMP NOT NULL,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    device_ids_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS traced_targets (
    id SERIAL PRIMARY KEY,
    target TEXT NOT NULL,
    port TEXT,
    traced_at TIMESTAMP,
    note TEXT,
    UNIQUE (target, port)
);

CREATE TABLE IF NOT EXISTS imports (
    id SERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    rows_inserted INTEGER,
    rows_skipped INTEGER,
    rows_failed INTEGER,
    total_rows INTEGER,
    parsed_rows INTEGER,
    raw_rows INTEGER,
    status TEXT,
    log TEXT,
    file_hash TEXT,
    queue_position INTEGER
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id TEXT,
    detail TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- ====== 依赖表（有外键） ======

CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT NOT NULL,
    is_permanent INTEGER NOT NULL DEFAULT 0,
    batch_id INTEGER REFERENCES tag_batches(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS mined_event_devices (
    event_id INTEGER REFERENCES mined_events(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    PRIMARY KEY (event_id, device_id)
);

CREATE TABLE IF NOT EXISTS mined_event_iocs (
    event_id INTEGER REFERENCES mined_events(id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    port TEXT,
    PRIMARY KEY (event_id, target, port)
);

CREATE TABLE IF NOT EXISTS event_followups (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES mined_events(id) ON DELETE CASCADE NOT NULL,
    action_type TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS device_tags (
    device_id TEXT NOT NULL,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (device_id, tag_id)
);

CREATE TABLE IF NOT EXISTS import_sheets (
    id SERIAL PRIMARY KEY,
    import_id INTEGER REFERENCES imports(id) ON DELETE CASCADE NOT NULL,
    sheet_name TEXT NOT NULL,
    sheet_index INTEGER NOT NULL,
    header_row INTEGER,
    headers_json TEXT,
    row_count INTEGER,
    parsed_rows INTEGER,
    raw_rows INTEGER,
    failed_rows INTEGER,
    status TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS import_rows (
    id SERIAL PRIMARY KEY,
    import_id INTEGER REFERENCES imports(id) ON DELETE CASCADE NOT NULL,
    import_sheet_id INTEGER REFERENCES import_sheets(id) ON DELETE CASCADE NOT NULL,
    source_file TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    excel_row_number INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    normalized_json TEXT,
    parse_status TEXT NOT NULL,
    parse_error TEXT,
    row_hash TEXT,
    alert_id INTEGER,
    created_at TIMESTAMP NOT NULL
);

-- ====== 索引 ======
CREATE INDEX IF NOT EXISTS idx_alerts_device_id ON alerts(device_id);
CREATE INDEX IF NOT EXISTS idx_alerts_source_ip ON alerts(source_ip);
CREATE INDEX IF NOT EXISTS idx_alerts_target ON alerts(target);
CREATE INDEX IF NOT EXISTS idx_alerts_first_alert_time ON alerts(first_alert_time);
CREATE INDEX IF NOT EXISTS idx_alerts_std_apt_org ON alerts(std_apt_org);
CREATE INDEX IF NOT EXISTS idx_alerts_threat_type ON alerts(threat_type);
CREATE INDEX IF NOT EXISTS idx_alerts_content_hash ON alerts(content_hash);
CREATE INDEX IF NOT EXISTS idx_alerts_imported_at ON alerts(imported_at);
CREATE INDEX IF NOT EXISTS idx_alerts_import_id ON alerts(import_id);
CREATE INDEX IF NOT EXISTS idx_alerts_import_row_id ON alerts(import_row_id);
CREATE INDEX IF NOT EXISTS idx_alerts_is_focused ON alerts(is_focused);
CREATE INDEX IF NOT EXISTS idx_alerts_heat_group ON alerts(device_id, target, source_ip);
CREATE INDEX IF NOT EXISTS idx_alerts_crossday ON alerts(source_ip, target, first_alert_time);

-- GIN 全文搜索索引
CREATE INDEX IF NOT EXISTS idx_alerts_search ON alerts USING gin(
    to_tsvector('simple',
        COALESCE(device_id, '') || ' ' ||
        COALESCE(source_ip, '') || ' ' ||
        COALESCE(target, '') || ' ' ||
        COALESCE(threat_type, '') || ' ' ||
        COALESCE(std_apt_org, '') || ' ' ||
        COALESCE(apt_org, '')
    )
);

CREATE INDEX IF NOT EXISTS idx_event_followups_event_id ON event_followups(event_id);
CREATE INDEX IF NOT EXISTS idx_event_iocs_lookup ON mined_event_iocs(target, port);
CREATE INDEX IF NOT EXISTS idx_device_tags_lookup ON device_tags(device_id, tag_id);
CREATE INDEX IF NOT EXISTS idx_import_sheets_import_id ON import_sheets(import_id);
CREATE INDEX IF NOT EXISTS idx_import_rows_import_id ON import_rows(import_id);
CREATE INDEX IF NOT EXISTS idx_import_rows_sheet_id ON import_rows(import_sheet_id);
CREATE INDEX IF NOT EXISTS idx_import_rows_status ON import_rows(parse_status);
CREATE INDEX IF NOT EXISTS idx_traced_target_port ON traced_targets(target, port);
