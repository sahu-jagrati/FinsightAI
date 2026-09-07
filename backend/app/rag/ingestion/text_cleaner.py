"""text_cleaner — normalizes raw extracted text before chunking.

PDF text extraction is noisy: hyphenated words split across line breaks,
inconsistent whitespace, and stray control characters. This stays
intentionally conservative — it normalizes whitespace and de-hyphenates,
but does not try to strip repeated headers/footers or reflow paragraphs,
since being too aggressive risks deleting real financial figures.
"""

import re
import unicodedata

_HYPHENATED_LINEBREAK_RE = re.compile(r"(\w)-\n(\w)")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_CHARS_RE.sub("", text)

    # "invest-\nment" -> "investment"
    text = _HYPHENATED_LINEBREAK_RE.sub(r"\1\2", text)

    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)

    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()
