"""chunker — structure-aware semantic chunking (Section 6).

Not a fixed 500-character splitter. This walks the document line by line,
tracks the most recent section heading (detected heuristically — short,
title-cased or all-caps lines that don't end in punctuation, e.g. "Revenue"
or "MANAGEMENT'S DISCUSSION AND ANALYSIS"), and produces overlapping
word-windows so a chunk near a boundary still has context on both sides.
Every chunk keeps the page number and section it came from.

"Tokens" here means whitespace-split words, not a model-specific tokenizer
— close enough for chunk-sizing purposes and avoids pulling in a tokenizer
dependency just to pick chunk boundaries. Swapping in `tiktoken` later
would only change `_word_count`, not the rest of the algorithm.
"""

import re
from dataclasses import dataclass

from app.core.config import settings

_HEADING_RE = re.compile(r"^[A-Z0-9][A-Za-z0-9 ,&/'()\-]{1,79}$")


@dataclass
class Chunk:
    chunk_index: int
    content: str
    page_number: int | None
    section: str | None
    token_count: int


@dataclass
class _Word:
    text: str
    page_number: int
    section: str | None


@dataclass
class PageLike:
    """Minimal shape `chunk_document` needs — satisfied by both
    `ParsedPage` and any (page_number, text) pair after cleaning."""

    page_number: int
    text: str


def _looks_like_heading(line: str) -> bool:
    if not line or len(line) > 80:
        return False
    if line.endswith((".", ",", ";", ":")):
        return False
    words = line.split()
    if not (1 <= len(words) <= 8):
        return False
    if line.isupper():
        return True
    # Title Case: most words start with a capital letter.
    capitalized = sum(1 for w in words if w[:1].isupper())
    return capitalized >= max(1, len(words) - 1)


def _tokenize_with_context(pages: list[PageLike]) -> list[_Word]:
    words: list[_Word] = []
    current_section: str | None = None

    for page in pages:
        for raw_line in page.text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if _looks_like_heading(line):
                current_section = line
                continue
            for w in line.split(" "):
                if w:
                    words.append(_Word(w, page.page_number, current_section))

    return words


def chunk_document(
    pages: list[PageLike],
    *,
    chunk_size_words: int | None = None,
    overlap_words: int | None = None,
) -> list[Chunk]:
    chunk_size_words = chunk_size_words or settings.CHUNK_SIZE_TOKENS
    overlap_words = overlap_words if overlap_words is not None else settings.CHUNK_OVERLAP_TOKENS
    overlap_words = min(overlap_words, chunk_size_words - 1) if chunk_size_words > 1 else 0

    words = _tokenize_with_context(pages)
    if not words:
        return []

    step = max(1, chunk_size_words - overlap_words)
    chunks: list[Chunk] = []
    i = 0
    n = len(words)

    while i < n:
        window = words[i : i + chunk_size_words]
        if not window:
            break

        chunks.append(
            Chunk(
                chunk_index=len(chunks),
                content=" ".join(w.text for w in window),
                page_number=window[0].page_number,
                section=window[0].section,
                token_count=len(window),
            )
        )
        i += step

    return chunks
