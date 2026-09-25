"""Shared HTTP GET for tools: retries transient failures, maps errors to ApiError."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .errors import ApiError

USER_AGENT = "bestiary/0.1"
RETRY_CODES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
RETRY_DELAY = 3.0  # doubles per attempt: 3s, 6s, 12s


class HttpError(ApiError):
    """A non-2xx response that survived retries. Keeps the status and body."""

    def __init__(self, service: str, code: int, body: bytes) -> None:
        reason = {404: "not found", 429: "rate limited"}.get(code, "http error")
        super().__init__(f"{service} {reason} ({code})")
        self.code = code
        self.body = body


def fetch(
    url: str,
    service: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retry_codes: frozenset[int] = RETRY_CODES,
    timeout: int = 30,
) -> tuple[str, bytes]:
    """GET url and return (final_url_after_redirects, body).

    `params` entries set to None are dropped. `service` names the API in errors.
    """
    query = {k: v for k, v in (params or {}).items() if v is not None}
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    attempt = 1
    while True:
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.geturl(), response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in retry_codes and attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY * 2 ** (attempt - 1))
                attempt += 1
                continue
            raise HttpError(service, exc.code, exc.read()) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"{service} request failed: {exc.reason}") from exc


def get_json(url: str, service: str, **kwargs: Any) -> Any:
    return json.loads(fetch(url, service, **kwargs)[1])
