"""Smoke tests — unit-test validation paths without hitting the network."""

from __future__ import annotations

import pytest

from bestiary.core.errors import ValidationError
from bestiary.tools import stackexchange


def test_search_requires_query():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="search")


def test_search_query_too_long():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="search", query="x" * 501)


def test_search_rejects_invalid_site():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="search", query="ok", site="StackOverflow!")


def test_search_rejects_too_many_tags():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(
            op="search", query="ok", tagged="a;b;c;d;e;f"
        )


def test_search_rejects_bad_tag():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="search", query="ok", tagged="not a tag!")


def test_search_rejects_bad_sort():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="search", query="ok", sort="popular")  # type: ignore[arg-type]


def test_search_rejects_non_bool_accepted():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="search", query="ok", accepted="yes")  # type: ignore[arg-type]


def test_question_requires_id():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="question")


def test_question_rejects_non_positive_id():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="question", question_id=0)


def test_question_rejects_bool_id():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="question", question_id=True)  # type: ignore[arg-type]


def test_invalid_op_rejected():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="bogus")  # type: ignore[arg-type]


def test_limit_out_of_range():
    with pytest.raises(ValidationError):
        stackexchange.stackexchange(op="search", query="ok", limit=200)


def test_strip_html_preserves_inline_code():
    text = stackexchange._strip_html("<p>Use <code>x = 1</code> here.</p>")
    assert "`x = 1`" in text


def test_strip_html_preserves_pre_block():
    text = stackexchange._strip_html("<pre><code>def f():\n    pass</code></pre>")
    assert "```" in text
    assert "def f()" in text
