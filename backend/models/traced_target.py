from sqlalchemy import Column, Integer, Text, DateTime, UniqueConstraint
from backend.models import Base


class TracedTarget(Base):
    __tablename__ = "traced_targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target = Column(Text, nullable=False)
    port = Column(Text, nullable=True)
    traced_at = Column(DateTime, nullable=True)
    note = Column(Text)
    __table_args__ = (UniqueConstraint("target", "port"),)
