"""Smoke tests — unit-test validation paths without hitting the network."""

from __future__ import annotations

import pytest

from bestiary.core.errors import ValidationError
from bestiary.tools import youtube


def test_transcript_requires_video():
    with pytest.raises(ValidationError):
        youtube.youtube(op="transcript")


def test_list_requires_video():
    with pytest.raises(ValidationError):
        youtube.youtube(op="list")


def test_invalid_video_string():
    with pytest.raises(ValidationError):
        youtube.youtube(op="transcript", video="not-a-url-or-id")


def test_invalid_op_rejected():
    with pytest.raises(ValidationError):
        youtube.youtube(op="bogus")  # type: ignore[arg-type]


def test_max_chars_out_of_range():
    with pytest.raises(ValidationError):
        youtube.youtube(op="transcript", video="jNQXAC9IVRw", max_chars=10)


def test_too_many_languages():
    with pytest.raises(ValidationError):
        youtube.youtube(
            op="transcript",
            video="jNQXAC9IVRw",
            languages=["en"] * 11,
        )


def test_invalid_language_code():
    with pytest.raises(ValidationError):
        youtube.youtube(
            op="transcript", video="jNQXAC9IVRw", languages=["english"]
        )


def test_extract_id_from_raw_id():
    assert youtube._extract_video_id("jNQXAC9IVRw") == "jNQXAC9IVRw"


def test_extract_id_from_watch_url():
    assert (
        youtube._extract_video_id("https://www.youtube.com/watch?v=jNQXAC9IVRw")
        == "jNQXAC9IVRw"
    )


def test_extract_id_from_watch_url_with_extra_params():
    assert (
        youtube._extract_video_id(
            "https://www.youtube.com/watch?feature=share&v=jNQXAC9IVRw&t=10s"
        )
        == "jNQXAC9IVRw"
    )


def test_extract_id_from_short_url():
    assert (
        youtube._extract_video_id("https://youtu.be/jNQXAC9IVRw?t=5")
        == "jNQXAC9IVRw"
    )


def test_extract_id_from_embed_url():
    assert (
        youtube._extract_video_id("https://www.youtube.com/embed/jNQXAC9IVRw")
        == "jNQXAC9IVRw"
    )


def test_extract_id_from_shorts_url():
    assert (
        youtube._extract_video_id("https://www.youtube.com/shorts/jNQXAC9IVRw")
        == "jNQXAC9IVRw"
    )


def test_extract_id_from_mobile_url():
    assert (
        youtube._extract_video_id("https://m.youtube.com/watch?v=jNQXAC9IVRw")
        == "jNQXAC9IVRw"
    )


def test_languages_comma_string_normalized():
    assert youtube._normalize_languages("en,es,pt-BR") == ["en", "es", "pt-BR"]


def test_languages_default_when_none():
    assert youtube._normalize_languages(None) == ["en"]


def test_format_timestamp_under_hour():
    assert youtube._format_timestamp(75.4) == "01:15"


def test_format_timestamp_with_hours():
    assert youtube._format_timestamp(3725.0) == "01:02:05"


def test_default_cookies_is_chrome(monkeypatch):
    monkeypatch.delenv("BESTIARY_YT_COOKIES_FROM_BROWSER", raising=False)
    assert youtube._parse_cookies_env() == ("chrome", None)


def test_cookies_env_override_browser(monkeypatch):
    monkeypatch.setenv("BESTIARY_YT_COOKIES_FROM_BROWSER", "firefox")
    assert youtube._parse_cookies_env() == ("firefox", None)


def test_cookies_env_with_profile(monkeypatch):
    monkeypatch.setenv("BESTIARY_YT_COOKIES_FROM_BROWSER", "firefox:/tmp/p")
    assert youtube._parse_cookies_env() == ("firefox", "/tmp/p")


def test_cookies_can_be_disabled(monkeypatch):
    monkeypatch.setenv("BESTIARY_YT_COOKIES_FROM_BROWSER", "none")
    assert youtube._parse_cookies_env() is None


def test_ydl_opts_defaults_to_chrome(monkeypatch):
    monkeypatch.delenv("BESTIARY_YT_COOKIES_FROM_BROWSER", raising=False)
    opts = youtube._ydl_opts()
    assert opts.get("cookiesfrombrowser") == ("chrome",)
