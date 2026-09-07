from app.rag.ingestion.text_cleaner import clean_text


def test_dehyphenates_across_linebreaks():
    assert clean_text("invest-\nment") == "investment"


def test_collapses_excess_whitespace():
    assert clean_text("Revenue   was    high") == "Revenue was high"
    assert clean_text("a\n\n\n\n\nb") == "a\n\nb"


def test_strips_control_characters():
    assert clean_text("Net\x00income\x07") == "Netincome"


def test_empty_input():
    assert clean_text("") == ""
    assert clean_text(None) == ""  # type: ignore[arg-type]
