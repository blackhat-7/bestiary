"""Slack archive stats — read-only SQL over a local slackdump archive.

The archive is a SQLite database produced by `slackdump archive`
(https://github.com/rusq/slackdump).  This tool only ever opens it
read-only; refreshing the archive itself is a CLI-side job
(`slackdump resume`), not something an agent should do here.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ..core.errors import ApiError, ValidationError
from ..core.validation import bounded_int, enum_value, name_string

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

ARCHIVE = os.environ.get("SLACKDUMP_ARCHIVE", "~/.slack-archive/slackdump.sqlite")

SlackOp = Literal["channels", "users", "messages_per_day", "top_users", "search"]

# Slack IDs are C/UD-prefixed alphanumerics; validate before they touch SQL.
_MAX_QUERY_LEN = 200
_MAX_TEXT_SHOWN = 500


def _connect() -> sqlite3.Connection:
    path = Path(ARCHIVE).expanduser()
    if not path.is_file():
        raise ApiError(
            f"slack archive not found at {path} — run `slackdump archive` first "
            "(auth via `slackdump workspace new`, refresh via `slackdump resume`)"
        )
    # mode=ro: the connection physically cannot write, even if SQL says so.
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _channel_map(con: sqlite3.Connection) -> dict[str, str]:
    """Latest name per channel (resume appends chunks, so names repeat)."""
    rows = con.execute(
        "SELECT ID, MAX(NAME) FROM CHANNEL GROUP BY ID"
    ).fetchall()
    return {ch_id: (name or ch_id) for ch_id, name in rows}


def _user_map(con: sqlite3.Connection) -> dict[str, str]:
    rows = con.execute(
        "SELECT ID, USERNAME FROM S_USER GROUP BY ID"
    ).fetchall()
    return {user_id: username for user_id, username in rows}


def _message_meta(data: bytes) -> tuple[str, str]:
    """Return (user_id, text) from the full Slack message JSON blob."""
    try:
        msg = json.loads(data)
    except (ValueError, TypeError):
        return "?", ""
    user = msg.get("user") or msg.get("bot_id") or "?"
    return user, (msg.get("text") or "")


def _msg_count_expr() -> str:
    # MESSAGE.ID is the numeric timestamp; the (ID, CHUNK_ID) PK means a
    # resumed channel appears in several chunks — count distinct per channel.
    return "COUNT(DISTINCT ID || '|' || CHANNEL_ID)"


def _ts_window(con: sqlite3.Connection, days: int) -> str | None:
    """Slack ts prefix (unix seconds) for the oldest message to include."""
    if days is None:
        return None
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return str(int(cutoff.timestamp()))


def _slack_stats(
    con: sqlite3.Connection,
    op: str,
    channel: str | None,
    query: str | None,
    days: int | None,
    limit: int,
) -> Any:
    channels = _channel_map(con)
    users = _user_map(con)
    since = _ts_window(con, days)
    cond = " AND CHANNEL_ID = ? AND TS >= ?" if (channel and since) else \
           " AND CHANNEL_ID = ?" if channel else \
           " AND TS >= ?" if since else ""
    args: tuple[str, ...] = ()
    if channel and since:
        args = (channel, since)
    elif channel:
        args = (channel,)
    elif since:
        args = (since,)

    if op == "channels":
        rows = con.execute(
            f"""
            SELECT CHANNEL_ID, {_msg_count_expr()}
            FROM MESSAGE
            WHERE CHANNEL_ID IS NOT NULL {cond}
            GROUP BY CHANNEL_ID
            ORDER BY 2 DESC
            LIMIT ?
            """,
            args + (limit,),
        ).fetchall()
        return [
            {"channel": channels.get(ch_id, ch_id), "channel_id": ch_id, "messages": n}
            for ch_id, n in rows
        ]

    if op == "users":
        rows = con.execute(
            "SELECT ID, USERNAME FROM S_USER GROUP BY ID ORDER BY USERNAME LIMIT ?",
            (limit,),
        ).fetchall()
        return [{"user_id": user_id, "username": username} for user_id, username in rows]

    if op == "messages_per_day":
        rows = con.execute(
            f"""
            SELECT substr(TS, 1, 10), {_msg_count_expr()}
            FROM MESSAGE
            WHERE TS IS NOT NULL {cond}
            GROUP BY 1
            ORDER BY 1 DESC
            LIMIT ?
            """,
            args + (limit,),
        ).fetchall()
        return [
            {
                "day": datetime.fromtimestamp(int(day), tz=timezone.utc).date().isoformat(),
                "messages": n,
            }
            for day, n in rows
        ]

    if op == "top_users":
        rows = con.execute(
            f"SELECT DATA FROM MESSAGE WHERE DATA IS NOT NULL {cond}",
            args,
        ).fetchall()
        counter: Counter[str] = Counter()
        for (data,) in rows:
            user, _ = _message_meta(data)
            counter[user] += 1
        return [
            {"user_id": user_id, "username": users.get(user_id, "?"), "messages": n}
            for user_id, n in counter.most_common(limit)
        ]

    # op == "search"
    like = f"%{query}%"
    rows = con.execute(
        f"""
        SELECT ID, CHANNEL_ID, TXT, DATA
        FROM MESSAGE
        WHERE TXT LIKE ? {cond}
        ORDER BY TS DESC
        LIMIT ?
        """,
        (like,) + args + (limit,),
    ).fetchall()
    results = []
    for ts, ch_id, txt, data in rows:
        user, text = _message_meta(data)
        results.append(
            {
                "channel": channels.get(ch_id, ch_id or "?"),
                "channel_id": ch_id,
                "ts": ts,
                "user": users.get(user, "?"),
                "text": (txt or text or "")[:_MAX_TEXT_SHOWN],
            }
        )
    return results


def slack_stats(
    op: SlackOp,
    channel: str | None = None,
    query: str | None = None,
    days: int | None = 30,
    limit: int = 20,
) -> Any:
    """Read-only stats over the local slackdump archive (SQLite).

    Operations:
      - channels:          most active channels, newest first by message count.
                           optional: days (window), limit.
      - users:             all workspace users in the archive.
                           optional: limit.
      - messages_per_day:  message counts per day (UTC). optional: channel,
                           days (default 30), limit.
      - top_users:         most active posters. optional: channel, days, limit.
      - search:            substring search over message text. required: query.
                           optional: channel, days, limit.

    The archive is read-only here; it is refreshed out-of-band via
    `slackdump resume` (see the slackdump skill).
    """
    op_v = enum_value(op, "op", set(SlackOp.__args__))  # type: ignore[attr-defined]
    channel_v = name_string(channel, "channel") if channel else None
    if query is not None:
        if not isinstance(query, str) or not query or len(query) > _MAX_QUERY_LEN:
            raise ValidationError("invalid query")
    if op_v == "search" and not query:
        raise ValidationError("search requires a query")
    days_v = bounded_int(days, "days", minimum=1, maximum=3650)
    limit_v = bounded_int(limit, "limit", minimum=1, maximum=100) or 20

    with _connect() as con:
        return _slack_stats(con, op_v, channel_v, query, days_v, limit_v)


def register(mcp: "FastMCP") -> None:
    mcp.tool()(slack_stats)
