from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, PrimaryKeyConstraint, UniqueConstraint
from backend.models import Base


class MinedEvent(Base):
    __tablename__ = "mined_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_name = Column(Text, nullable=False)
    color = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")
    mined_at = Column(DateTime, nullable=False)
    note = Column(Text)


class MinedEventDevice(Base):
    __tablename__ = "mined_event_devices"

    event_id = Column(Integer, ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(Text, nullable=False)
    __table_args__ = (PrimaryKeyConstraint("event_id", "device_id"),)


class MinedEventIoc(Base):
    __tablename__ = "mined_event_iocs"

    event_id = Column(Integer, ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False)
    target = Column(Text, nullable=False)
    port = Column(Text, nullable=True)
    __table_args__ = (PrimaryKeyConstraint("event_id", "target", "port"),)


class EventFollowup(Base):
    __tablename__ = "event_followups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("mined_events.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)
    note = Column(Text)
