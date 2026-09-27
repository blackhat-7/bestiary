"""Smoke tests — validation and auth paths without hitting the network."""

from __future__ import annotations

import json
import urllib.request

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


def test_requires_credentials(monkeypatch):
    monkeypatch.setattr(reddit, "_token", None)
    monkeypatch.delenv(reddit.ID_ENV, raising=False)
    monkeypatch.delenv(reddit.SECRET_ENV, raising=False)
    with pytest.raises(ApiError, match=reddit.ID_ENV):
        reddit.reddit(op="subreddit", subreddit="python")


class _Response:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def geturl(self):
        return "https://x"

    def read(self):
        return self._body


def test_logs_in_once_and_calls_oauth_api(monkeypatch):
    monkeypatch.setattr(reddit, "_token", None)
    monkeypatch.setenv(reddit.ID_ENV, "id")
    monkeypatch.setenv(reddit.SECRET_ENV, "secret")
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if request.full_url == reddit.TOKEN_URL:
            return _Response({"access_token": "tok", "expires_in": 3600})
        return _Response({"data": {"display_name": "python"}})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    reddit.reddit(op="subreddit", subreddit="python")
    reddit.reddit(op="subreddit", subreddit="python")

    login, *api_calls = requests
    assert login.full_url == reddit.TOKEN_URL
    assert login.data == b"grant_type=client_credentials"
    assert len(api_calls) == 2
    assert api_calls[-1].full_url.startswith(f"{reddit.API_URL}/r/python/about?")
    assert api_calls[-1].get_header("Authorization") == "Bearer tok"


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
