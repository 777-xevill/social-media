"""HTTP helper, error types and secret-safe logging."""
from __future__ import annotations

import os
import time

import requests

USER_AGENT = "social-autopilot/1.0"
_SECRETS: list[str] = []


class ApiError(Exception):
    """A platform rejected a request. `auth=True` means credentials need attention."""

    def __init__(self, platform: str, message: str, status: int | None = None, auth: bool = False):
        self.platform, self.status, self.auth = platform, status, auth
        super().__init__(scrub(f"[{platform}] {f'HTTP {status}: ' if status else ''}{message}"))


class NotReady(Exception):
    """Temporary condition (e.g. media not on GitHub Pages yet) — try again next run."""


def register_secrets(values: list[str]) -> None:
    _SECRETS.extend(v for v in values if v not in _SECRETS)


def scrub(text: str) -> str:
    for s in _SECRETS:
        text = text.replace(s, "***")
    return text


def log(msg: str, level: str = "info") -> None:
    msg = scrub(msg)
    if os.environ.get("GITHUB_ACTIONS") and level in ("warning", "error"):
        print(f"::{level}::{msg}", flush=True)
    else:
        print(("⚠ " if level == "warning" else "✖ " if level == "error" else "") + msg, flush=True)


def request(method: str, url: str, platform: str, *, timeout: int = 120, **kw) -> requests.Response:
    """requests.request with GET retries on transient errors and ApiError on failure."""
    headers = {"User-Agent": USER_AGENT, **(kw.pop("headers", None) or {})}
    tries = 3 if method.upper() in ("GET", "HEAD") else 1
    for attempt in range(tries):
        try:
            r = requests.request(method, url, headers=headers, timeout=timeout, **kw)
        except requests.RequestException as e:
            if attempt + 1 < tries:
                time.sleep(2 ** attempt * 2)
                continue
            raise ApiError(platform, f"network error: {e}") from e
        if r.status_code in (429, 500, 502, 503, 504) and attempt + 1 < tries:
            time.sleep(2 ** attempt * 3)
            continue
        if r.status_code >= 400:
            raise ApiError(platform, _error_text(r), r.status_code, auth=r.status_code in (401, 403))
        return r
    raise AssertionError("unreachable")


def _error_text(r: requests.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        return r.text[:500] or r.reason
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return err.get("error_user_msg") or err.get("message") or str(err)[:500]
    if isinstance(body, dict):
        return str(body.get("message") or body.get("error_description") or err or body)[:500]
    return str(body)[:500]
