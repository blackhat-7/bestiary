"""Smoke tests for the slack archive stats tool against a synthetic DB."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from bestiary.core.errors import ApiError, ValidationError
from bestiary.tools import slack


def _make_archive(path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE CHANNEL (ID TEXT, NAME TEXT);
        CREATE TABLE S_USER (ID TEXT, USERNAME TEXT);
        CREATE TABLE MESSAGE (
            ID INTEGER, CHANNEL_ID TEXT, TS TEXT, TXT TEXT, DATA BLOB
        );
        """
    )
    users = [("U1", "alice"), ("U2", "bob")]
    channels = [("C1", "general"), ("C2", "random")]
    now = int(datetime.now(timezone.utc).timestamp())
    msgs = [
        # (id, channel, ts, text, user) — ids/ts are unix seconds, near now
        (now - 300, "C1", f"{now - 300}.000001", "hello world", "U1"),
        (now - 200, "C1", f"{now - 200}.000001", "deploy went fine", "U2"),
        (now - 100, "C1", f"{now - 100}.000001", "see https://x.dev", "U1"),
        (now - 50, "C2", f"{now - 50}.000001", "random chatter", "U2"),
    ]
    con.executemany("INSERT INTO CHANNEL VALUES (?, ?)", channels)
    con.executemany("INSERT INTO S_USER VALUES (?, ?)", users)
    con.executemany(
        "INSERT INTO MESSAGE VALUES (?, ?, ?, ?, ?)",
        [
            (mid, ch, ts, txt, json.dumps({"user": user}).encode())
            for mid, ch, ts, txt, user in msgs
        ],
    )
    con.commit()
    con.close()


@pytest.fixture
def archive(tmp_path, monkeypatch):
    path = tmp_path / "slackdump.sqlite"
    _make_archive(path)
    monkeypatch.setattr(slack, "ARCHIVE", str(path))
    return path


def test_channels_sorted_by_activity(archive):
    result = slack.slack_stats(op="channels")
    assert result[0]["channel"] == "general"
    assert result[0]["messages"] == 3
    assert result[1]["channel"] == "random"


def test_channel_filter(archive):
    result = slack.slack_stats(op="channels", channel="C2")
    assert [r["channel"] for r in result] == ["random"]
    assert result[0]["messages"] == 1


def test_messages_per_day(archive):
    result = slack.slack_stats(op="messages_per_day", days=365)
    # all four messages are within minutes of now; they may straddle midnight UTC
    assert sum(r["messages"] for r in result) == 4
    assert all(r["messages"] >= 1 for r in result)


def test_top_users_parses_message_blob(archive):
    result = slack.slack_stats(op="top_users")
    assert result[0]["username"] == "alice"
    assert result[0]["messages"] == 2
    assert result[1]["username"] == "bob"


def test_search(archive):
    result = slack.slack_stats(op="search", query="deploy")
    assert len(result) == 1
    assert result[0]["channel"] == "general"
    assert result[0]["user"] == "bob"


def test_search_requires_query(archive):
    with pytest.raises(ValidationError):
        slack.slack_stats(op="search")


def test_invalid_op(archive):
    with pytest.raises(ValidationError):
        slack.slack_stats(op="bogus")  # type: ignore[arg-type]


def test_missing_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(slack, "ARCHIVE", str(tmp_path / "nope.sqlite"))
    with pytest.raises(ApiError):
        slack.slack_stats(op="channels")
