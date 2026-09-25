"""Reddit tool — read-only access to Reddit's public JSON endpoints.

Reddit 403s logged-out JSON requests since May 2026, so requests carry the
`reddit_session` cookie from a logged-in browser, read from $REDDIT_SESSION.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any, Literal

from ..core.errors import ApiError, ValidationError
from ..core.validation import bounded_int, enum_value, name_string

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

BASE_URL = "https://www.reddit.com"
USER_AGENT = "bestiary/0.1 (reddit-json-client)"
SESSION_ENV = "REDDIT_SESSION"

# Retry rate limits and transient server errors with doubling delays.
_RETRY_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_RETRY_DELAY = 2.0

RedditOp = Literal["search", "posts", "subreddit", "post", "user"]
TimeRange = Literal["hour", "day", "week", "month", "year", "all"]
SortValue = Literal[
    "relevance", "hot", "top", "new", "comments", "rising", "controversial"
]

_SEARCH_SORTS = {"relevance", "hot", "top", "new", "comments"}
_POST_SORTS = {"hot", "new", "top", "rising", "controversial"}
_TIME_VALUES = {"hour", "day", "week", "month", "year", "all"}


def _api_get(path: str, params: dict[str, Any] | None = None) -> Any:
    session = os.environ.get(SESSION_ENV)
    if not session:
        raise ApiError(
            f"{SESSION_ENV} is not set: copy the reddit_session cookie from a "
            "browser logged into reddit.com"
        )
    query = urllib.parse.urlencode({"raw_json": "1", **(params or {})})
    request = urllib.request.Request(
        f"{BASE_URL}/{path}.json?{query}",
        headers={"User-Agent": USER_AGENT, "Cookie": f"reddit_session={session}"},
    )
    attempt = 1
    while True:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRY_CODES and attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAY * 2 ** (attempt - 1))
                attempt += 1
                continue
            if exc.code == 404:
                raise ApiError(f"not found: {path}") from exc
            if exc.code == 429:
                raise ApiError("rate limited by Reddit") from exc
            if exc.code == 403:
                raise ApiError(
                    f"reddit http error: 403 ({SESSION_ENV} may be expired or invalid)"
                ) from exc
            raise ApiError(f"reddit http error: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"reddit request failed: {exc.reason}") from exc


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
    """Read Reddit (public JSON endpoints, authenticated via $REDDIT_SESSION).

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
