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


def _ts_bounds(
    days: int | None, start: str | None, end: str | None
) -> tuple[str | None, str | None]:
    """Return (from_ts, to_ts) Slack ts prefixes for the query window.

    Either `days` (counting back from now) or `start`/`end` dates
    (YYYY-MM-DD, inclusive, UTC) set the window; `days` is ignored when
    `start`/`end` are given.  A ts prefix is the integer unix seconds part
    of a Slack ts like "1700000000.000001" — comparisons are textual and
    correct because the seconds part is fixed-width.
    """
    if start or end:
        start_ts = str(int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())) if start else None
        end_ts = (
            str(
                int(
                    (
                        datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
                        + timedelta(days=1)
                    ).timestamp()
                )
            )
            if end
            else None
        )
        return start_ts, end_ts
    if days is None:
        return None, None
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return str(int(cutoff.timestamp())), None


def _validate_date(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"invalid {key}: expected YYYY-MM-DD") from None
    return value


def _slack_stats(
    con: sqlite3.Connection,
    op: str,
    channel: str | None,
    query: str | None,
    ts_from: str | None,
    ts_to: str | None,
    limit: int,
) -> Any:
    channels = _channel_map(con)
    users = _user_map(con)
    cond = " AND CHANNEL_ID = ?" if channel else ""
    cond += " AND TS >= ?" if ts_from else ""
    cond += " AND TS < ?" if ts_to else ""
    args: tuple[str, ...] = ()
    if channel:
        args += (channel,)
    if ts_from:
        args += (ts_from,)
    if ts_to:
        args += (ts_to,)

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
    start: str | None = None,
    end: str | None = None,
    limit: int = 20,
) -> Any:
    """Read-only stats over the local slackdump archive (SQLite).

    Operations:
      - channels:          most active channels by message count.
                           optional: days, start/end (window), limit.
      - users:             all workspace users in the archive.
                           optional: limit.
      - messages_per_day:  message counts per day (UTC). optional: channel,
                           days, start/end, limit.
      - top_users:         most active posters. optional: channel, days,
                           start/end, limit.
      - search:            substring search over message text. required: query.
                           optional: channel, days, start/end, limit.

    Window: `days` counts back from today (default 30). For absolute ranges
    use `start`/`end` (YYYY-MM-DD, inclusive, UTC) — `days` is ignored then.
    Long windows return the newest `limit` rows; to cover more, call again
    with a narrower start/end window.

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
    start_v = _validate_date(start, "start")
    end_v = _validate_date(end, "end")
    if start_v and end_v and start_v > end_v:
        raise ValidationError("start must be before end")
    limit_v = bounded_int(limit, "limit", minimum=1, maximum=100) or 20

    ts_from, ts_to = _ts_bounds(days_v, start_v, end_v)
    with _connect() as con:
        return _slack_stats(con, op_v, channel_v, query, ts_from, ts_to, limit_v)


def register(mcp: "FastMCP") -> None:
    mcp.tool()(slack_stats)
