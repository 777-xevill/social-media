"""Public URLs for media files (served by GitHub Pages) and basic file facts."""
from __future__ import annotations

import mimetypes
from pathlib import Path

import requests

from .config import Config
from .net import USER_AGENT, NotReady

_checked: dict[str, bool] = {}

mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("video/quicktime", ".mov")
mimetypes.add_type("image/webp", ".webp")


def mime(path: Path | str) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def public_url(cfg: Config, rel_path: str) -> str:
    """URL other services can download the file from. Raises NotReady until Pages serves it."""
    url = cfg.media_url(rel_path)
    if url not in _checked:
        try:
            r = requests.head(url, timeout=30, allow_redirects=True, headers={"User-Agent": USER_AGENT})
            _checked[url] = r.status_code == 200
        except requests.RequestException:
            _checked[url] = False
    if not _checked[url]:
        raise NotReady(f"{url} isn't live on GitHub Pages yet (it updates a minute or two after each push)")
    return url
