"""Reddit tool — read-only access to Reddit's JSON API.

Reddit 403s logged-out requests, so the tool logs in with app-only OAuth using
a "script" app's credentials (https://www.reddit.com/prefs/apps), read from
$REDDIT_CLIENT_ID and $REDDIT_CLIENT_SECRET.
"""

from __future__ import annotations

import base64
import json
import os
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal

from ..core import http
from ..core.errors import ApiError, ValidationError
from ..core.validation import bounded_int, enum_value, name_string

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

API_URL = "https://oauth.reddit.com"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
ID_ENV = "REDDIT_CLIENT_ID"
SECRET_ENV = "REDDIT_CLIENT_SECRET"

RedditOp = Literal["search", "posts", "subreddit", "post", "user"]
TimeRange = Literal["hour", "day", "week", "month", "year", "all"]
SortValue = Literal[
    "relevance", "hot", "top", "new", "comments", "rising", "controversial"
]

_SEARCH_SORTS = {"relevance", "hot", "top", "new", "comments"}
_POST_SORTS = {"hot", "new", "top", "rising", "controversial"}
_TIME_VALUES = {"hour", "day", "week", "month", "year", "all"}

_token: tuple[str, float] | None = None  # (access_token, monotonic expiry)


def _access_token() -> str:
    """Return a cached app-only OAuth token, fetching a new one when it expires."""
    global _token
    if _token is not None and monotonic() < _token[1]:
        return _token[0]
    client_id = os.environ.get(ID_ENV)
    secret = os.environ.get(SECRET_ENV)
    if not client_id or not secret:
        raise ApiError(
            f"{ID_ENV} and {SECRET_ENV} must be set: the credentials of a "
            "script app from https://www.reddit.com/prefs/apps"
        )
    basic = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    try:
        _, body = http.fetch(
            TOKEN_URL,
            "reddit login",
            data=b"grant_type=client_credentials",
            headers={"Authorization": f"Basic {basic}"},
        )
    except http.HttpError as exc:
        if exc.code == 401:
            raise ApiError(f"reddit login failed: check {ID_ENV} and {SECRET_ENV}") from exc
        raise
    data = json.loads(body)
    if "access_token" not in data:
        raise ApiError(f"reddit login failed: {data.get('error', 'no access_token')}")
    # Refresh a minute early so a token never expires mid-request.
    _token = (data["access_token"], monotonic() + data.get("expires_in", 3600) - 60)
    return _token[0]


def _api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    return http.get_json(
        f"{API_URL}/{path}",
        "reddit",
        params={"raw_json": "1", **(params or {})},
        headers={"Authorization": f"Bearer {_access_token()}"},
    )


def _clean_post(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data", raw)
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "subreddit": data.get("subreddit"),
        "author": data.get("author"),
        "score": data.get("score"),
        "upvote_ratio": data.get("upvote_ratio"),
        "comments": data.get("num_comments"),
        "permalink": f"https://reddit.com{data.get('permalink', '')}",
        "url": data.get("url"),
        "selftext": data.get("selftext") or "",
        "flair": data.get("link_flair_text"),
    }


def _listing_posts(listing: dict[str, Any]) -> list[dict[str, Any]]:
    return [_clean_post(item) for item in listing.get("children", [])]


def _flatten_comments(listing: dict[str, Any], depth: int = 0) -> list[dict[str, Any]]:
    """Walk a comment listing depth-first into a depth-tagged flat list.

    Skips "more" stubs (collapsed replies Reddit didn't send). A comment with
    no replies has `replies == ""` rather than an empty listing.
    """
    out: list[dict[str, Any]] = []
    for child in listing.get("data", {}).get("children", []):
        if child.get("kind") != "t1":
            continue
        data = child["data"]
        out.append(
            {
                "id": data.get("id"),
                "author": data.get("author"),
                "body": data.get("body") or "",
                "score": data.get("score"),
                "depth": depth,
            }
        )
        if isinstance(data.get("replies"), dict):
            out.extend(_flatten_comments(data["replies"], depth + 1))
    return out


def _clean_subreddit(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data", raw)
    return {
        "name": data.get("display_name"),
        "title": data.get("title"),
        "description": data.get("public_description") or "",
        "subscribers": data.get("subscribers"),
        "active_users": data.get("accounts_active"),
        "nsfw": data.get("over18"),
        "url": f"https://reddit.com/r/{data.get('display_name', '')}",
    }


def _clean_user(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data", raw)
    return {
        "name": data.get("name"),
        "link_karma": data.get("link_karma"),
        "comment_karma": data.get("comment_karma"),
        "verified": data.get("verified"),
        "is_mod": data.get("is_mod"),
    }


def _do_search(
    query: str | None,
    subreddit: str | None,
    sort: str | None,
    time: str | None,
    limit: int | None,
) -> dict[str, Any]:
    if not query:
        raise ValidationError("missing or invalid query")
    sub = name_string(subreddit, "subreddit")
    sort = enum_value(sort, "sort", _SEARCH_SORTS) or "relevance"
    time = enum_value(time, "time", _TIME_VALUES) or "all"
    limit = bounded_int(limit, "limit", minimum=1, maximum=100) or 10

    params = {"q": query, "sort": sort, "t": time, "limit": limit}
    path = "search"
    if sub is not None:
        path = f"r/{sub}/search"
        params["restrict_sr"] = "1"

    listing = _api_get(path, params).get("data", {})
    return {"items": _listing_posts(listing), "next_cursor": listing.get("after")}


def _do_posts(
    subreddit: str | None, sort: str | None, limit: int | None
) -> dict[str, Any]:
    sub = name_string(subreddit, "subreddit")
    if sub is None:
        raise ValidationError("missing or invalid subreddit")
    sort = enum_value(sort, "sort", _POST_SORTS) or "hot"
    limit = bounded_int(limit, "limit", minimum=1, maximum=100) or 10
    listing = _api_get(f"r/{sub}/{sort}", {"limit": limit}).get("data", {})
    return {"items": _listing_posts(listing), "next_cursor": listing.get("after")}


def _do_subreddit(subreddit: str | None) -> dict[str, Any]:
    sub = name_string(subreddit, "subreddit")
    if sub is None:
        raise ValidationError("missing or invalid subreddit")
    return _clean_subreddit(_api_get(f"r/{sub}/about"))


def _do_post(post_id: str | None, comments: int | None) -> dict[str, Any]:
    if not isinstance(post_id, str) or not (
        5 <= len(post_id) <= 12 and post_id.isascii() and post_id.isalnum()
    ):
        raise ValidationError("invalid post_id")
    n = bounded_int(comments, "comments", minimum=1, maximum=100) or 20
    response = _api_get(f"comments/{post_id}", {"limit": n})
    if not isinstance(response, list) or len(response) < 2:
        raise ApiError("unexpected reddit post response")
    post_listing = response[0].get("data", {}).get("children", [])
    if not post_listing:
        raise ApiError("post not found")
    return {
        "post": _clean_post(post_listing[0]),
        "comments": _flatten_comments(response[1])[:n],
    }


def _do_user(username: str | None, posts: int | None) -> dict[str, Any]:
    name = name_string(username, "username", allow_dash=True)
    if name is None:
        raise ValidationError("missing or invalid username")
    n = bounded_int(posts, "posts", minimum=1, maximum=100) or 10
    about = _clean_user(_api_get(f"user/{name}/about"))
    listing = _api_get(f"user/{name}/submitted", {"limit": n}).get("data", {})
    return {"user": about, "posts": _listing_posts(listing)}


def reddit(
    op: RedditOp,
    query: str | None = None,
    subreddit: str | None = None,
    sort: SortValue | None = None,
    time: TimeRange | None = None,
    limit: int | None = None,
    post_id: str | None = None,
    comments: int | None = None,
    username: str | None = None,
    posts: int | None = None,
) -> dict[str, Any]:
    """Read Reddit (JSON API, logged in via $REDDIT_CLIENT_ID/$REDDIT_CLIENT_SECRET).

    Operations:
      - search:    full-text search posts. required: query. optional: subreddit, sort, time, limit.
      - posts:     list posts in a subreddit. required: subreddit. optional: sort, limit.
      - subreddit: subreddit metadata. required: subreddit.
      - post:      a post and its comment tree, flattened depth-first into a
                   depth-tagged list. required: post_id.
                   optional: comments (max returned, 1-100, default 20).
      - user:      user profile + recent submissions. required: username. optional: posts.
    """
    if op == "search":
        return _do_search(query, subreddit, sort, time, limit)
    if op == "posts":
        return _do_posts(subreddit, sort, limit)
    if op == "subreddit":
        return _do_subreddit(subreddit)
    if op == "post":
        return _do_post(post_id, comments)
    if op == "user":
        return _do_user(username, posts)
    raise ValidationError("invalid op")


def register(mcp: "FastMCP") -> None:
    mcp.tool()(reddit)
