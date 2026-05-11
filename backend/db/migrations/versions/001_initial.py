"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-04-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("tag_batches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("batch_name", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    op.create_table("tags",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("color", sa.Text, nullable=False),
        sa.Column("is_permanent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("tag_batches.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    op.create_table("device_tags",
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.PrimaryKeyConstraint("device_id", "tag_id"),
    )

    op.create_table("mined_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_name", sa.Text, nullable=False),
        sa.Column("color", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="'active'"),
        sa.Column("mined_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )

    op.create_table("mined_event_devices",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("event_id", "device_id"),
    )

    op.create_table("mined_event_iocs",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("port", sa.Text),
        sa.UniqueConstraint("event_id", "target", "port"),
    )

    op.create_table("event_followups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("note", sa.Text),
    )
    op.create_index("idx_followup_event", "event_followups", ["event_id"])

    op.create_table("traced_targets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("port", sa.Text),
        sa.Column("traced_at", sa.DateTime),
        sa.Column("note", sa.Text),
        sa.UniqueConstraint("target", "port"),
    )
    op.create_index("idx_traced_target", "traced_targets", ["target"])

    op.create_table("alerts",
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
        sa.Column("dns_resolved_ip", sa.Text),
        sa.Column("down_traffic", sa.Integer),
        sa.Column("up_traffic", sa.Integer),
        sa.Column("asset_type", sa.Text),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("imported_at", sa.DateTime, nullable=False),
        sa.Column("unique_hash", sa.Text, unique=True),
    )
    op.create_index("idx_alerts_device_id", "alerts", ["device_id"])
    op.create_index("idx_alerts_source_ip", "alerts", ["source_ip"])
    op.create_index("idx_alerts_target", "alerts", ["target"])
    op.create_index("idx_alerts_imported_at", "alerts", ["imported_at"])
    op.create_index("idx_alerts_first_alert_time", "alerts", ["first_alert_time"])
    op.create_index("idx_alerts_std_apt_org", "alerts", ["std_apt_org"])
    op.create_index("idx_alerts_crossday", "alerts", ["source_ip", "target", "first_alert_time"])

    op.create_table("imports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_file", sa.Text, nullable=False),
        sa.Column("imported_at", sa.DateTime, nullable=False),
        sa.Column("rows_inserted", sa.Integer),
        sa.Column("rows_skipped", sa.Integer),
        sa.Column("rows_failed", sa.Integer),
        sa.Column("status", sa.Text),
        sa.Column("log", sa.Text),
    )

    op.create_table("audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text),
        sa.Column("target_id", sa.Text),
        sa.Column("detail", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("imports")
    op.drop_table("alerts")
    op.drop_table("traced_targets")
    op.drop_table("event_followups")
    op.drop_table("mined_event_iocs")
    op.drop_table("mined_event_devices")
    op.drop_table("mined_events")
    op.drop_table("device_tags")
    op.drop_table("tags")
    op.drop_table("tag_batches")
