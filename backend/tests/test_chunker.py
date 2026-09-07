from app.rag.ingestion.chunker import PageLike, chunk_document


def _page(n: int, text: str) -> PageLike:
    return PageLike(page_number=n, text=text)


def test_empty_input_returns_no_chunks():
    assert chunk_document([]) == []
    assert chunk_document([_page(1, "")]) == []


def test_single_short_page_is_one_chunk():
    page = _page(1, "Revenue\nApple reported strong revenue growth this quarter.")
    chunks = chunk_document([page], chunk_size_words=50, overlap_words=5)

    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert chunks[0].section == "Revenue"
    assert "revenue growth" in chunks[0].content


def test_heading_detection_updates_section_for_subsequent_lines():
    text = (
        "Overview\n"
        "The company performed well.\n"
        "Risk Factors\n"
        "Supply chain risk remains elevated."
    )
    chunks = chunk_document([_page(1, text)], chunk_size_words=100, overlap_words=0)

    assert len(chunks) == 1
    # Last word's section wins as the window's own section tag is taken
    # from the FIRST word in the window, so re-chunk with a tiny window to
    # observe section switching directly.
    small_chunks = chunk_document([_page(1, text)], chunk_size_words=4, overlap_words=0)
    sections = [c.section for c in small_chunks]
    assert "Overview" in sections
    assert "Risk Factors" in sections


def test_long_document_produces_overlapping_chunks():
    words = " ".join(f"word{i}" for i in range(200))
    chunks = chunk_document([_page(1, words)], chunk_size_words=50, overlap_words=10)

    assert len(chunks) > 1
    # consecutive chunks should share the overlap region
    first_tail = chunks[0].content.split()[-10:]
    second_head = chunks[1].content.split()[:10]
    assert first_tail == second_head


def test_chunks_track_page_number_across_pages():
    chunks = chunk_document(
        [_page(1, "alpha beta gamma"), _page(2, "delta epsilon zeta")],
        chunk_size_words=3,
        overlap_words=0,
    )
    page_numbers = {c.page_number for c in chunks}
    assert page_numbers == {1, 2}


def test_heading_like_body_sentence_is_not_misdetected():
    # Ends in a period and is a full sentence -> should NOT be treated as
    # a heading even though it starts with a capital letter.
    text = "Total revenue increased significantly during the fiscal year."
    chunks = chunk_document([_page(1, text)], chunk_size_words=50, overlap_words=0)
    assert chunks[0].section is None
