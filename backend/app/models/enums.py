"""Shared enums used by ORM models and Pydantic schemas alike (imported by
both so the API and the database always agree on valid values).
"""

import enum


class DocumentType(str, enum.Enum):
    ANNUAL_REPORT = "annual_report"
    QUARTERLY_REPORT = "quarterly_report"
    SEC_FILING = "sec_filing"
    EARNINGS_REPORT = "earnings_report"
    NEWS = "news"
    OTHER = "other"


class DocumentStatus(str, enum.Enum):
    """Section 4 pipeline: Uploaded -> Parsing -> Chunking -> Embedding -> Indexed."""

    UPLOADED = "uploaded"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXED = "indexed"
    FAILED = "failed"


TERMINAL_DOCUMENT_STATUSES = {DocumentStatus.INDEXED, DocumentStatus.FAILED}
