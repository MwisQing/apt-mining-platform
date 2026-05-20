from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, Index
from backend.models import Base


class Import(Base):
    __tablename__ = "imports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_file = Column(Text, nullable=False)
    imported_at = Column(DateTime, nullable=False)
    rows_inserted = Column(Integer)
    rows_skipped = Column(Integer)
    rows_failed = Column(Integer)
    total_rows = Column(Integer)
    parsed_rows = Column(Integer)
    raw_rows = Column(Integer)
    status = Column(Text)
    log = Column(Text)


class ImportSheet(Base):
    __tablename__ = "import_sheets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    import_id = Column(Integer, ForeignKey("imports.id", ondelete="CASCADE"), nullable=False)
    sheet_name = Column(Text, nullable=False)
    sheet_index = Column(Integer, nullable=False)
    header_row = Column(Integer)
    headers_json = Column(Text)
    row_count = Column(Integer)
    parsed_rows = Column(Integer)
    raw_rows = Column(Integer)
    failed_rows = Column(Integer)
    status = Column(Text)
    created_at = Column(DateTime, nullable=False)


class ImportRow(Base):
    __tablename__ = "import_rows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    import_id = Column(Integer, ForeignKey("imports.id", ondelete="CASCADE"), nullable=False)
    import_sheet_id = Column(Integer, ForeignKey("import_sheets.id", ondelete="CASCADE"), nullable=False)
    source_file = Column(Text, nullable=False)
    sheet_name = Column(Text, nullable=False)
    excel_row_number = Column(Integer, nullable=False)
    raw_json = Column(Text, nullable=False)
    normalized_json = Column(Text)
    parse_status = Column(Text, nullable=False)
    parse_error = Column(Text)
    row_hash = Column(Text)
    alert_id = Column(Integer)
    created_at = Column(DateTime, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(Text, nullable=False)
    target_type = Column(Text)
    target_id = Column(Text)
    detail = Column(Text)
    created_at = Column(DateTime, nullable=False)


Index("idx_import_sheets_import_id", ImportSheet.import_id)
Index("idx_import_rows_import_id", ImportRow.import_id)
Index("idx_import_rows_sheet_id", ImportRow.import_sheet_id)
Index("idx_import_rows_status", ImportRow.parse_status)
