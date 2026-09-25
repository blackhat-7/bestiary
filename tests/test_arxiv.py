"""Smoke tests — unit-test validation paths without hitting the network."""

from __future__ import annotations

import urllib.error

import pytest

from bestiary.core.errors import ApiError, ValidationError
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


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, None)


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def geturl(self):
        return "https://x"

    def read(self):
        return b"ok"


def test_http_fetch_retries_transient_errors(monkeypatch):
    outcomes = [_http_error(406), _http_error(503), _FakeResponse()]

    def fake_urlopen(request, timeout):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(arxiv.time, "sleep", lambda _: None)
    assert arxiv._http_fetch("https://x") == ("https://x", b"ok")


def test_http_fetch_gives_up_after_max_attempts(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(1)
        raise _http_error(406)

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(arxiv.time, "sleep", lambda _: None)
    with pytest.raises(ApiError, match="406"):
        arxiv._http_fetch("https://x")
    assert len(calls) == arxiv._MAX_ATTEMPTS


def test_http_fetch_does_not_retry_404(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(1)
        raise _http_error(404)

    monkeypatch.setattr(arxiv.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ApiError, match="not found"):
        arxiv._http_fetch("https://x")
    assert len(calls) == 1
