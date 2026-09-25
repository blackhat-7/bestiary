"""Smoke tests — unit-test validation paths without hitting the network."""

from __future__ import annotations

import pytest

from bestiary.core.errors import ApiError, ValidationError
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


def test_requires_session_cookie(monkeypatch):
    monkeypatch.delenv(reddit.SESSION_ENV, raising=False)
    with pytest.raises(ApiError, match=reddit.SESSION_ENV):
        reddit.reddit(op="subreddit", subreddit="python")


def _comment(id: str, replies: object = "") -> dict:
    return {"kind": "t1", "data": {"id": id, "body": id, "replies": replies}}


def _listing(*children: dict) -> dict:
    return {"data": {"children": list(children)}}


def test_flatten_comments_walks_reply_tree_depth_first():
    tree = _listing(
        _comment("a", _listing(_comment("a1", _listing(_comment("a1x"))))),
        {"kind": "more", "data": {}},
        _comment("b"),
    )
    flat = reddit._flatten_comments(tree)
    assert [(c["id"], c["depth"]) for c in flat] == [
        ("a", 0),
        ("a1", 1),
        ("a1x", 2),
        ("b", 0),
    ]

