"""Retry and error mapping for the shared HTTP helper, without the network."""

from __future__ import annotations

import urllib.error

import pytest

from bestiary.core import http


def _error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "err", {}, None)


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def geturl(self):
        return "https://x"

    def read(self):
        return b'{"ok": true}'


@pytest.fixture
def urlopen(monkeypatch):
    """Replay `outcomes` (exceptions raised, responses returned) in order."""
    outcomes: list = []

    def fake(request, timeout):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(http.urllib.request, "urlopen", fake)
    monkeypatch.setattr(http.time, "sleep", lambda _: None)
    return outcomes


def test_retries_transient_errors(urlopen):
    urlopen += [_error(429), _error(503), _Response()]
    assert http.get_json("https://x", "svc") == {"ok": True}
    assert not urlopen


def test_gives_up_after_max_attempts(urlopen):
    urlopen += [_error(503)] * http.MAX_ATTEMPTS
    with pytest.raises(http.HttpError, match="svc http error") as info:
        http.fetch("https://x", "svc")
    assert info.value.code == 503
    assert not urlopen


def test_does_not_retry_other_errors(urlopen):
    urlopen += [_error(404)]
    with pytest.raises(http.HttpError, match="svc not found"):
        http.fetch("https://x", "svc")


def test_extra_retry_codes(urlopen):
    urlopen += [_error(406), _Response()]
    assert http.fetch("https://x", "svc", retry_codes=http.RETRY_CODES | {406})[1]
