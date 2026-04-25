"""Smoke tests — unit-test validation paths without hitting the network."""

from __future__ import annotations

import pytest

from bestiary.core.errors import ValidationError
from bestiary.tools import reddit


def test_search_requires_query():
    with pytest.raises(ValidationError):
        reddit.reddit(op="search")


def test_posts_requires_subreddit():
    with pytest.raises(ValidationError):
        reddit.reddit(op="posts")


def test_subreddit_rejects_bad_name():
    with pytest.raises(ValidationError):
        reddit.reddit(op="subreddit", subreddit="not a name!")


def test_post_id_must_be_alphanum():
    with pytest.raises(ValidationError):
        reddit.reddit(op="post", post_id="bad/id")


def test_user_requires_username():
    with pytest.raises(ValidationError):
        reddit.reddit(op="user")


def test_invalid_op_rejected():
    with pytest.raises(ValidationError):
        reddit.reddit(op="bogus")  # type: ignore[arg-type]


def test_limit_out_of_range():
    with pytest.raises(ValidationError):
        reddit.reddit(op="posts", subreddit="python", limit=200)
