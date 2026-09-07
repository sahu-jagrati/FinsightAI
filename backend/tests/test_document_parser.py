import pytest
from fpdf import FPDF

from app.core.exceptions import CorruptedDocumentError, EmptyDocumentError
from app.rag.ingestion.document_parser import parse_document


def test_parse_txt(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Revenue grew 12% year over year.", encoding="utf-8")

    doc = parse_document(str(path), ".txt")

    assert doc.page_count == 1
    assert "Revenue grew 12%" in doc.full_text


def test_parse_html_strips_tags_and_scripts(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        "<html><body><script>evil()</script><h1>Q4 Results</h1>"
        "<p>Net income was $5B.</p></body></html>",
        encoding="utf-8",
    )

    doc = parse_document(str(path), ".html")

    assert "Q4 Results" in doc.full_text
    assert "Net income was $5B." in doc.full_text
    assert "evil()" not in doc.full_text


def test_parse_real_pdf(tmp_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="Apple annual revenue was $394,328 million in fiscal 2022.")
    pdf_path = tmp_path / "report.pdf"
    pdf.output(str(pdf_path))

    doc = parse_document(str(pdf_path), ".pdf")

    assert doc.page_count == 1
    assert "394,328" in doc.full_text


def test_parse_empty_txt_raises(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("   \n  ", encoding="utf-8")

    with pytest.raises(EmptyDocumentError):
        parse_document(str(path), ".txt")


def test_parse_corrupted_pdf_raises(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not actually a pdf")

    with pytest.raises(CorruptedDocumentError):
        parse_document(str(path), ".pdf")
