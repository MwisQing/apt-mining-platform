from sqlalchemy import Column, Integer, Text, ForeignKey, UniqueConstraint, Index

from backend.models import Base


class AlertCandidateSnapshot(Base):
    __tablename__ = "alert_candidate_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_version = Column(Text, nullable=False)

    device_id = Column(Text, nullable=False)
    target = Column(Text, nullable=False)
    port = Column(Text, nullable=False, default="")

    source_ip = Column(Text)
    source_ips = Column(Text)
    source_ip_count = Column(Integer, default=0)

    target_type = Column(Text)
    target_kind = Column(Text)
    target_kind_label = Column(Text)

    threat_type = Column(Text)
    threat_level = Column(Text)
    std_apt_org = Column(Text)
    apt_org = Column(Text)
    apt_org_tier = Column(Text)
    vendors = Column(Text)
    protocol = Column(Text)
    intel_tags = Column(Text)
    dns_resolved_ip = Column(Text)
    asset_type = Column(Text)

    analysis_status = Column(Text, default="")
    is_focused = Column(Integer, default=0)

    alert_count = Column(Integer, default=0)
    first_alert_time = Column(Text)
    last_alert_time = Column(Text)

    heat_target_alert_count = Column(Integer, default=0)
    heat_target_device_count = Column(Integer, default=0)
    heat_device_alert_count = Column(Integer, default=0)
    heat_device_target_count = Column(Integer, default=0)
    heat_source_ip_alert_count = Column(Integer, default=0)

    candidate_score = Column(Integer, default=0)
    candidate_priority = Column(Text)
    candidate_priority_label = Column(Text)
    candidate_rule_ids_json = Column(Text)
    candidate_reasons_json = Column(Text)

    event_json = Column(Text)
    event_status = Column(Text)
    trace_json = Column(Text)
    trace_status = Column(Text)
    ioc_note = Column(Text)

    cross_day = Column(Integer, default=0)
    lateral = Column(Integer, default=0)

    heat_summary_json = Column(Text)
    relation_summary = Column(Text)
    candidate_summary = Column(Text)
    candidate_focus = Column(Text)
    device_note_summary = Column(Text)

    sort_priority_rank = Column(Integer, default=0)
    sort_rule_hits = Column(Integer, default=0)
    sort_target_device_count = Column(Integer, default=0)
    sort_target_alert_count = Column(Integer, default=0)
    sort_source_ip_alert_count = Column(Integer, default=0)
    sort_trace_status = Column(Text)
    sort_event_status = Column(Text)

    updated_at = Column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("snapshot_version", "device_id", "target", "port"),
    )


class AlertCandidateSnapshotBadge(Base):
    __tablename__ = "alert_candidate_snapshot_badges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_version = Column(Text, nullable=False)
    snapshot_id = Column(Integer, ForeignKey("alert_candidate_snapshots.id", ondelete="CASCADE"), nullable=False)
    badge_name = Column(Text, nullable=False)
    badge_label = Column(Text, nullable=False)
    badge_color = Column(Text)


class AlertCandidateSnapshotTag(Base):
    __tablename__ = "alert_candidate_snapshot_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_version = Column(Text, nullable=False)
    snapshot_id = Column(Integer, ForeignKey("alert_candidate_snapshots.id", ondelete="CASCADE"), nullable=False)
    tag_id = Column(Integer, nullable=False)
    tag_name = Column(Text, nullable=False)
    tag_color = Column(Text)


class SnapshotBuildMeta(Base):
    __tablename__ = "snapshot_build_meta"

    snapshot_type = Column(Text, primary_key=True)
    active_version = Column(Text)
    building_version = Column(Text)
    status = Column(Text, nullable=False, default="idle")
    last_built_at = Column(Text)
    last_build_started_at = Column(Text)
    last_build_duration_ms = Column(Integer, default=0)
    last_row_count = Column(Integer, default=0)
    last_error = Column(Text)


Index("idx_snap_version_first_time", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.first_alert_time)
Index("idx_snap_version_score", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.candidate_score)
Index("idx_snap_version_target_type", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.target_type)
Index("idx_snap_version_threat_type", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.threat_type)
Index("idx_snap_version_threat_level", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.threat_level)
Index("idx_snap_version_apt_tier", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.apt_org_tier)
Index("idx_snap_version_trace", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.trace_status)
Index("idx_snap_version_priority", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.candidate_priority)
Index("idx_snap_version_target", AlertCandidateSnapshot.snapshot_version, AlertCandidateSnapshot.target)

Index("idx_snap_badges_version_name", AlertCandidateSnapshotBadge.snapshot_version, AlertCandidateSnapshotBadge.badge_name)
Index("idx_snap_badges_version_snapshot", AlertCandidateSnapshotBadge.snapshot_version, AlertCandidateSnapshotBadge.snapshot_id)
Index("idx_snap_tags_version_tag", AlertCandidateSnapshotTag.snapshot_version, AlertCandidateSnapshotTag.tag_id)
Index("idx_snap_tags_version_name", AlertCandidateSnapshotTag.snapshot_version, AlertCandidateSnapshotTag.tag_name)
Index("idx_snap_tags_version_snapshot", AlertCandidateSnapshotTag.snapshot_version, AlertCandidateSnapshotTag.snapshot_id)
