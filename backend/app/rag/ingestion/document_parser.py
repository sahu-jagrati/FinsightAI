"""document_parser — extracts raw per-page text from a file on disk.

One function per format, dispatched by extension. PDF is the priority
format (Section 4); TXT/HTML/Markdown are supported too since Section 2
lists them as accepted uploads. Table extraction / layout-aware parsing is
a possible future improvement — today this is text-only, which is enough
for semantic chunking + retrieval.
"""

from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.exceptions import CorruptedDocumentError, EmptyDocumentError


@dataclass
class ParsedPage:
    page_number: int  # 1-indexed
    text: str


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)


def _parse_pdf(path: Path) -> ParsedDocument:
    try:
        reader = PdfReader(str(path))
    except (PdfReadError, OSError) as exc:
        raise CorruptedDocumentError(f"Could not read PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise CorruptedDocumentError("PDF is password-protected.") from exc

    pages: list[ParsedPage] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - a single bad page shouldn't fail the doc
            text = ""
        pages.append(ParsedPage(page_number=i, text=text))

    return ParsedDocument(pages=pages)


def _parse_plain_text(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    return ParsedDocument(pages=[ParsedPage(page_number=1, text=text)])


def _parse_html(path: Path) -> ParsedDocument:
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return ParsedDocument(pages=[ParsedPage(page_number=1, text=text)])


_PARSERS = {
    ".pdf": _parse_pdf,
    ".txt": _parse_plain_text,
    ".md": _parse_plain_text,
    ".html": _parse_html,
    ".htm": _parse_html,
}


def parse_document(file_path: str, extension: str) -> ParsedDocument:
    parser = _PARSERS.get(extension)
    if parser is None:
        raise CorruptedDocumentError(f"No parser registered for '{extension}'.")

    doc = parser(Path(file_path))

    if doc.page_count == 0 or not doc.full_text.strip():
        raise EmptyDocumentError("The document contains no extractable text.")

    return doc
