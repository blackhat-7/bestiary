"""Smoke tests — unit-test validation paths without hitting the network."""

from __future__ import annotations

import pytest

from bestiary.core.errors import ValidationError
from bestiary.tools import arxiv


def test_search_requires_query():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="search")


def test_search_rejects_blank_query():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="search", query="   ")


def test_search_query_too_long():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="search", query="x" * 501)


def test_search_max_results_out_of_range():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="search", query="ml", max_results=100)


def test_search_invalid_category():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="search", query="ml", category="not a cat")


def test_search_invalid_sort_by():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="search", query="ml", sort_by="bogus")  # type: ignore[arg-type]


def test_search_invalid_sort_order():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="search", query="ml", sort_order="sideways")  # type: ignore[arg-type]


def test_metadata_requires_paper_id():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="metadata")


def test_metadata_rejects_bad_id():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="metadata", paper_id="not-an-id")


def test_read_requires_paper_id():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="read")


def test_read_max_chars_below_min():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="read", paper_id="2403.12345", max_chars=100)


def test_invalid_op_rejected():
    with pytest.raises(ValidationError):
        arxiv.arxiv(op="bogus")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "pid",
    [
        "2403.12345",
        "2403.12345v2",
        "1804.0123",
        "math.AG/0703456",
        "hep-th/0001034",
        "cond-mat/9901234v3",
    ],
)
def test_paper_id_accepts_valid_forms(pid: str):
    assert arxiv._validate_paper_id(pid) == pid


@pytest.mark.parametrize(
    "pid",
    [
        "",
        "abc",
        "12345.6789",
        "2403.123",
        "MATH/0703456",
        "math.AG/070345",
        "../etc/passwd",
        "2403.12345 ; rm -rf /",
    ],
)
def test_paper_id_rejects_invalid_forms(pid: str):
    with pytest.raises(ValidationError):
        arxiv._validate_paper_id(pid)


def test_text_extractor_strips_scripts_and_styles():
    parser = arxiv._TextExtractor()
    parser.feed(
        "<html><head><title>x</title><style>body{color:red}</style></head>"
        "<body><script>evil()</script><p>Hello <b>world</b></p>"
        "<p>Second paragraph.</p></body></html>"
    )
    text = parser.text()
    assert "Hello world" in text
    assert "Second paragraph." in text
    assert "evil" not in text
    assert "color:red" not in text


def test_text_extractor_decodes_entities():
    parser = arxiv._TextExtractor()
    parser.feed("<p>caf&eacute; &amp; tea</p>")
    assert "café & tea" in parser.text()
