from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from backend.models import Base


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    color = Column(Text, nullable=False)
    is_permanent = Column(Integer, nullable=False, default=0)
    batch_id = Column(Integer, ForeignKey("tag_batches.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, nullable=False)
    note = Column(Text)


class TagBatch(Base):
    __tablename__ = "tag_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_name = Column(Text)
    created_at = Column(DateTime, nullable=False)
    note = Column(Text)
    status = Column(Text, nullable=False, default="active")
    device_ids_snapshot = Column(Text)


class DeviceTag(Base):
    __tablename__ = "device_tags"

    device_id = Column(Text, nullable=False)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False)
    __table_args__ = (PrimaryKeyConstraint("device_id", "tag_id"),)
