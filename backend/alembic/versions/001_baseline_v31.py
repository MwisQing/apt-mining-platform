"""Baseline schema for v3.1

Revision ID: 001_baseline_v31
Revises:
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa

revision = "001_baseline_v31"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alerts
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("first_alert_time", sa.DateTime, nullable=False),
        sa.Column("last_alert_time", sa.DateTime, nullable=False),
        sa.Column("source_ip", sa.Text, nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text),
        sa.Column("port", sa.Text),
        sa.Column("threat_type", sa.Text),
        sa.Column("threat_level", sa.Text),
        sa.Column("std_apt_org", sa.Text),
        sa.Column("apt_org", sa.Text),
        sa.Column("apt_org_tier", sa.Text),
        sa.Column("alert_count", sa.Integer),
        sa.Column("vendors", sa.Text),
        sa.Column("protocol", sa.Text),
        sa.Column("intel_tags", sa.Text),
        sa.Column("intel_position", sa.Text),
        sa.Column("disposal_action", sa.Text),
        sa.Column("dns_resolved_ip", sa.Text),
        sa.Column("down_traffic", sa.Integer),
        sa.Column("up_traffic", sa.Integer),
        sa.Column("asset_type", sa.Text),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("imported_at", sa.DateTime, nullable=False),
        sa.Column("unique_hash", sa.Text, unique=True),
        sa.Column("content_hash", sa.Text),
        sa.Column("import_id", sa.Integer),
        sa.Column("import_sheet_id", sa.Integer),
        sa.Column("import_row_id", sa.Integer),
        sa.Column("sheet_name", sa.Text),
        sa.Column("excel_row_number", sa.Integer),
        sa.Column("raw_row_hash", sa.Text),
        sa.Column("analysis_status", sa.Text, server_default=""),
        sa.Column("is_focused", sa.Integer, server_default="0"),
    )

    # mined_events
    op.create_table(
        "mined_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_name", sa.Text, nullable=False),
        sa.Column("color", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("mined_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    # mined_event_devices
    op.create_table(
        "mined_event_devices",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("event_id", "device_id"),
    )

    # mined_event_iocs
    op.create_table(
        "mined_event_iocs",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("port", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("event_id", "target", "port"),
    )

    # event_followups
    op.create_table(
        "event_followups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    # tags
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("color", sa.Text, nullable=False),
        sa.Column("is_permanent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("tag_batches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    # tag_batches
    op.create_table(
        "tag_batches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("batch_name", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("device_ids_snapshot", sa.Text),
    )

    # device_tags
    op.create_table(
        "device_tags",
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint("device_id", "tag_id"),
    )

    # traced_targets
    op.create_table(
        "traced_targets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("port", sa.Text, nullable=True),
        sa.Column("traced_at", sa.DateTime, nullable=True),
        sa.Column("note", sa.Text),
        sa.UniqueConstraint("target", "port"),
    )

    # imports
    op.create_table(
        "imports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("imported_at", sa.DateTime, nullable=False),
        sa.Column("rows_inserted", sa.Integer),
        sa.Column("rows_skipped", sa.Integer),
        sa.Column("rows_failed", sa.Integer),
        sa.Column("total_rows", sa.Integer),
        sa.Column("parsed_rows", sa.Integer),
        sa.Column("raw_rows", sa.Integer),
        sa.Column("status", sa.Text),
        sa.Column("log", sa.Text),
    )

    # import_sheets
    op.create_table(
        "import_sheets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("import_id", sa.Integer, sa.ForeignKey("imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sheet_name", sa.Text, nullable=False),
        sa.Column("sheet_index", sa.Integer, nullable=False),
        sa.Column("header_row", sa.Integer),
        sa.Column("headers_json", sa.Text),
        sa.Column("row_count", sa.Integer),
        sa.Column("parsed_rows", sa.Integer),
        sa.Column("raw_rows", sa.Integer),
        sa.Column("failed_rows", sa.Integer),
        sa.Column("status", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # import_rows
    op.create_table(
        "import_rows",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("import_id", sa.Integer, sa.ForeignKey("imports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("import_sheet_id", sa.Integer, sa.ForeignKey("import_sheets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("sheet_name", sa.Text, nullable=False),
        sa.Column("excel_row_number", sa.Integer, nullable=False),
        sa.Column("raw_json", sa.Text, nullable=False),
        sa.Column("normalized_json", sa.Text),
        sa.Column("parse_status", sa.Text, nullable=False),
        sa.Column("parse_error", sa.Text),
        sa.Column("row_hash", sa.Text),
        sa.Column("alert_id", sa.Integer),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text),
        sa.Column("target_id", sa.Text),
        sa.Column("detail", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # Indexes
    op.create_index("idx_alerts_device_id", "alerts", ["device_id"])
    op.create_index("idx_alerts_source_ip", "alerts", ["source_ip"])
    op.create_index("idx_alerts_target", "alerts", ["target"])
    op.create_index("idx_alerts_imported_at", "alerts", ["imported_at"])
    op.create_index("idx_alerts_first_alert_time", "alerts", ["first_alert_time"])
    op.create_index("idx_alerts_std_apt_org", "alerts", ["std_apt_org"])
    op.create_index("idx_alerts_crossday", "alerts", ["source_ip", "target", "first_alert_time"])
    op.create_index("idx_alerts_content_hash", "alerts", ["content_hash"])
    op.create_index("idx_alerts_import_id", "alerts", ["import_id"])
    op.create_index("idx_alerts_import_row_id", "alerts", ["import_row_id"])
    op.create_index("idx_alerts_is_focused", "alerts", ["is_focused"])
    op.create_index("idx_alerts_threat_type", "alerts", ["threat_type"])
    op.create_index("idx_import_sheets_import_id", "import_sheets", ["import_id"])
    op.create_index("idx_import_rows_import_id", "import_rows", ["import_id"])
    op.create_index("idx_import_rows_sheet_id", "import_rows", ["import_sheet_id"])
    op.create_index("idx_import_rows_status", "import_rows", ["parse_status"])


def downgrade() -> None:
    # For safety baseline downgrade is no-op.
    # Users should use backups instead.
    pass
