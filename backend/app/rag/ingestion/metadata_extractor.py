"""metadata_extractor — pulls structured metadata (Section 6) that gets
denormalized onto every chunk for fast filtering (company/year/document
type) without a join back to `documents`.

Most of this metadata (company, document_type) is already known from the
upload form and just needs threading through — `extract_year` is the one
piece that has to be parsed out of a free-form field.
"""

import re

_YEAR_RE = re.compile(r"(19|20)\d{2}")


def extract_year(reporting_period: str | None) -> int | None:
    """"2025" -> 2025, "Q4 2025" -> 2025, "FY2024" -> 2024, None -> None."""
    if not reporting_period:
        return None
    match = _YEAR_RE.search(reporting_period)
    return int(match.group()) if match else None
