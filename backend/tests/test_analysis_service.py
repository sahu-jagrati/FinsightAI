"""Pure-function unit tests for the Research History title heuristic
(`app.services.analysis_service.generate_title`) — no DB needed."""

import re

from app.services.analysis_service import generate_title


def test_short_query_is_used_verbatim():
    assert generate_title("What was Apple's revenue?") == "What was Apple's revenue?"


def test_long_query_is_truncated_on_a_word_boundary():
    query = (
        "Compare Apple's and Microsoft's revenue growth from 2022 to 2025 and "
        "explain the main drivers behind the difference in their margins."
    )
    title = generate_title(query)
    collapsed = re.sub(r"\s+", " ", query).strip()

    assert len(title) <= 200
    assert title.endswith("…")
    body = title[:-1]
    # `body` must be a clean prefix of the original text — the character
    # right after it in the source is either a space or the end of string,
    # never a mid-word cut.
    assert collapsed.startswith(body)
    assert len(collapsed) == len(body) or collapsed[len(body)] == " "


def test_collapses_internal_whitespace():
    assert generate_title("What   was\nApple's   revenue?") == "What was Apple's revenue?"


def test_empty_query_falls_back_to_placeholder():
    assert generate_title("   ") == "Untitled research"
