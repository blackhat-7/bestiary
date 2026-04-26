"""Smoke tests — unit-test validation paths without hitting the network."""

from __future__ import annotations

import pytest

from bestiary.core.errors import ValidationError
from bestiary.tools import hackernews


def test_search_requires_query():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="search")


def test_search_query_too_long():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="search", query="x" * 501)


def test_search_invalid_sort():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="search", query="ok", sort="popular")  # type: ignore[arg-type]


def test_search_invalid_tag():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="search", query="ok", tag="random")  # type: ignore[arg-type]


def test_item_requires_id():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="item")


def test_item_rejects_non_positive():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="item", item_id=0)


def test_item_rejects_bool_id():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="item", item_id=True)  # type: ignore[arg-type]


def test_user_rejects_invalid_username():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="user", username="not a name!")


def test_invalid_op_rejected():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="bogus")  # type: ignore[arg-type]


def test_limit_out_of_range():
    with pytest.raises(ValidationError):
        hackernews.hackernews(op="search", query="ok", limit=200)


def test_strip_html_preserves_link_url():
    text = hackernews._strip_html(
        '<p>Check <a href="https://example.com/x">this</a> out.</p>'
    )
    assert "this" in text
    assert "https://example.com/x" in text
