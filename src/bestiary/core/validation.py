"""Input validators reused across tools."""

from __future__ import annotations

from typing import Iterable

from .errors import ValidationError


def name_string(value: str | None, key: str, *, allow_dash: bool = False) -> str | None:
    """Validate an alphanumeric identifier (subreddit, username, etc.).

    Returns None for None input. Raises ValidationError on invalid input.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 32:
        raise ValidationError(f"invalid {key}")
    extra = {"_", "-"} if allow_dash else {"_"}
    if not all(ch.isalnum() or ch in extra for ch in value):
        raise ValidationError(f"invalid {key}")
    return value


def bounded_int(value: int | None, key: str, *, minimum: int, maximum: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"invalid {key}")
    if value < minimum or value > maximum:
        raise ValidationError(f"invalid {key}")
    return value


def enum_value(value: str | None, key: str, allowed: Iterable[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in set(allowed):
        raise ValidationError(f"invalid {key}")
    return value
