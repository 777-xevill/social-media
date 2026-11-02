"""Settings (config.yaml) and secrets (env vars, GitHub Secrets JSON, local .env)."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
POSTS_DIR = CONTENT_DIR / "posts"
MEDIA_DIR = CONTENT_DIR / "media"
STATE_DIR = ROOT / "state"
ENV_FILE = ROOT / ".env"

PLATFORMS = [
    "facebook", "instagram", "threads", "youtube", "tiktok",
    "linkedin", "x", "pinterest", "reddit", "snapchat",
]
DEFAULT_VIA = {"x": "buffer", "tiktok": "buffer"}


class Config:
    def __init__(self, path: Path = ROOT / "config.yaml"):
        with open(path, encoding="utf-8") as f:
            self.raw: dict = yaml.safe_load(f) or {}
        self.tz = ZoneInfo(self.raw.get("timezone") or "UTC")
        self.site_url = self._site_url()

    def _site_url(self) -> str:
        url = (self.raw.get("site_url") or "").rstrip("/")
        repo = os.environ.get("GITHUB_REPOSITORY")
        if not url and repo:
            owner, name = repo.split("/", 1)
            url = f"https://{owner.lower()}.github.io/{name}"
        return url

    def platform(self, name: str) -> dict:
        cfg = dict((self.raw.get("platforms") or {}).get(name) or {})
        cfg.setdefault("enabled", False)
        cfg.setdefault("via", DEFAULT_VIA.get(name, "direct"))
        return cfg

    @property
    def default_platforms(self) -> list[str]:
        return list(self.raw.get("default_platforms") or [])

    @property
    def slots(self) -> list[dict]:
        return list((self.raw.get("schedule") or {}).get("slots") or [])

    @property
    def evergreen(self) -> dict:
        cfg = {"enabled": False, "idle_hours": 24, "min_days_between_reposts": 45}
        cfg.update(self.raw.get("evergreen") or {})
        return cfg

    @property
    def posting(self) -> dict:
        cfg = {"min_minutes_between_posts": 60, "max_attempts": 3, "low_queue_warning": 5}
        cfg.update(self.raw.get("posting") or {})
        return cfg

    @property
    def graph_version(self) -> str:
        return (self.raw.get("meta") or {}).get("graph_version", "v24.0")

    def media_url(self, rel_path: str) -> str:
        """Public URL of a file in content/media, served by GitHub Pages."""
        if not self.site_url:
            raise RuntimeError("site_url is not set in config.yaml")
        return f"{self.site_url}/content/media/{quote(rel_path.replace(os.sep, '/'))}"


class Secrets:
    """Looks up a secret in os.environ (Actions), then .env (local)."""

    def __init__(self):
        self._values: dict[str, str] = {}
        if ENV_FILE.exists():
            self._values.update({k: v for k, v in dotenv_values(ENV_FILE).items() if v})
        self._values.update({k: v for k, v in os.environ.items() if v})

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._values.get(key) or default

    def has(self, *keys: str) -> bool:
        return all(self.get(k) for k in keys)

    def missing(self, *keys: str) -> list[str]:
        return [k for k in keys if not self.get(k)]

    def sensitive_values(self) -> list[str]:
        return [v for k, v in self._values.items()
                if len(v) >= 8 and any(s in k for s in ("TOKEN", "SECRET", "PASSWORD", "KEY"))]
