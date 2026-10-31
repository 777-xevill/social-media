"""Post files (content/posts/*.md|yaml) and per-platform text rendering."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .config import MEDIA_DIR, PLATFORMS, POSTS_DIR

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm"}

# Caption length limits (characters).
TEXT_LIMITS = {
    "x": 280, "threads": 500, "instagram": 2200, "facebook": 60000, "linkedin": 3000,
    "tiktok": 2200, "youtube": 5000, "pinterest": 800, "reddit": 40000, "snapchat": 250,
}
# Platforms where a post's `link` is appended to the caption (others use a link field or drop it).
LINK_IN_TEXT = {"x", "threads", "youtube", "linkedin", "facebook", "snapchat"}
LINK_CARD = {"linkedin", "facebook"}
OVERRIDE_KEYS = {"text", "title", "link", "hashtags", "subreddit", "board_id", "alt", "video_format"}

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)
_URL = re.compile(r"https?://\S+")


class ContentError(ValueError):
    pass


@dataclass
class Post:
    key: str
    path: Path
    text: str = ""
    title: str = ""
    link: str = ""
    hashtags: list[str] = field(default_factory=list)
    media: list[str] = field(default_factory=list)
    publish_at: datetime | None = None
    platforms: list[str] | None = None
    evergreen: bool = False
    video_format: str = "short"          # short → Reels/Shorts/TikTok, long → regular video
    alt: str = ""
    overrides: dict[str, dict] = field(default_factory=dict)

    @property
    def images(self) -> list[str]:
        return [m for m in self.media if Path(m).suffix.lower() in IMAGE_EXT]

    @property
    def videos(self) -> list[str]:
        return [m for m in self.media if Path(m).suffix.lower() in VIDEO_EXT]

    @property
    def kind(self) -> str:
        """text | image | images | video | mixed"""
        imgs, vids = self.images, self.videos
        if not self.media:
            return "text"
        if vids and imgs or len(vids) > 1:
            return "mixed"
        if vids:
            return "video"
        return "image" if len(imgs) == 1 else "images"

    def targets(self, default_platforms: list[str]) -> list[str]:
        return list(self.platforms if self.platforms is not None else default_platforms)


@dataclass
class Rendered:
    """A post prepared for one platform."""
    platform: str
    post: Post
    text: str
    title: str
    link: str
    options: dict

    @property
    def media_paths(self) -> list[Path]:
        return [MEDIA_DIR / m for m in self.post.media]

    @property
    def is_short(self) -> bool:
        return self.options.get("video_format", self.post.video_format) != "long"


def load_posts(tz: ZoneInfo, posts_dir: Path = POSTS_DIR) -> tuple[dict[str, Post], list[str]]:
    """Returns ({key: Post}, [errors]). Files starting with `_` are examples and are ignored."""
    posts, errors = {}, []
    if not posts_dir.exists():
        return posts, errors
    for path in sorted(posts_dir.rglob("*")):
        if path.suffix.lower() not in (".md", ".yaml", ".yml") or path.name.startswith(("_", ".")):
            continue
        try:
            post = parse_post(path, tz, posts_dir)
        except (ContentError, yaml.YAMLError) as e:
            errors.append(f"{path.relative_to(posts_dir)}: {e}")
            continue
        if post.key in posts:
            errors.append(f"{path.name}: duplicate post name '{post.key}'")
            continue
        posts[post.key] = post
    return posts, errors


def parse_post(path: Path, tz: ZoneInfo, posts_dir: Path = POSTS_DIR) -> Post:
    raw = path.read_text(encoding="utf-8").lstrip("﻿")
    if path.suffix.lower() == ".md":
        m = _FRONTMATTER.match(raw)
        meta = yaml.safe_load(m.group(1)) if m else {}
        body = (m.group(2) if m else raw).strip()
        meta = meta or {}
        if body and "text" not in meta:
            meta["text"] = body
    else:
        meta = yaml.safe_load(raw) or {}
    if not isinstance(meta, dict):
        raise ContentError("expected key: value settings")

    key = str(path.relative_to(posts_dir).with_suffix("")).replace("\\", "/")
    post = Post(key=key, path=path)
    post.text = str(meta.get("text") or "").strip()
    post.title = str(meta.get("title") or "").strip()
    post.link = str(meta.get("link") or "").strip()
    post.alt = str(meta.get("alt") or "").strip()
    post.hashtags = _hashtags(meta.get("hashtags"))
    post.media = _list(meta.get("media"))
    post.evergreen = bool(meta.get("evergreen", False))
    post.video_format = str(meta.get("video_format") or "short").lower()
    if post.video_format not in ("short", "long"):
        raise ContentError("video_format must be 'short' or 'long'")
    post.publish_at = parse_when(meta.get("publish_at"), tz)

    if meta.get("platforms") is not None:
        post.platforms = [p.lower() for p in _list(meta["platforms"])]
        unknown = [p for p in post.platforms if p not in PLATFORMS]
        if unknown:
            raise ContentError(f"unknown platform(s) {unknown}; use: {', '.join(PLATFORMS)}")

    for name in PLATFORMS:
        if name in meta:
            ov = meta[name]
            if isinstance(ov, str):
                ov = {"text": ov}
            if not isinstance(ov, dict):
                raise ContentError(f"'{name}:' must be text or settings")
            bad = set(ov) - OVERRIDE_KEYS
            if bad:
                raise ContentError(f"'{name}:' has unknown setting(s) {sorted(bad)}")
            if "hashtags" in ov:
                ov["hashtags"] = _hashtags(ov["hashtags"])
            post.overrides[name] = ov

    if not post.text and not post.media and not post.link:
        raise ContentError("post has no text, media or link")
    return post


def parse_when(value, tz: ZoneInfo) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime.combine(value, time(10, 0))
    else:
        try:
            dt = datetime.fromisoformat(str(value).strip())
        except ValueError:
            raise ContentError(f"publish_at '{value}' is not a date like 2026-11-05 10:00") from None
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def render(post: Post, platform: str, pcfg: dict) -> Rendered:
    ov = post.overrides.get(platform, {})
    body = str(ov.get("text", post.text)).strip()
    link = str(ov.get("link", post.link)).strip()
    title = str(ov.get("title", post.title)).strip()
    max_tags = int(pcfg.get("max_hashtags", 5))
    tags = (ov.get("hashtags", post.hashtags) or [])[:max_tags]

    # Facebook and LinkedIn show text-only posts' links as a preview card instead.
    link_in_text = platform in LINK_IN_TEXT and not (platform in LINK_CARD and post.kind == "text")
    tail_parts = []
    if link and link_in_text and link not in body:
        tail_parts.append(link)
    if tags:
        tail_parts.append(" ".join("#" + t for t in tags))
    tail = "\n\n".join(tail_parts)
    text = _fit(body, tail, TEXT_LIMITS.get(platform, 5000), platform)

    if not title:
        first = _URL.sub("", body.split("\n", 1)[0]).strip() if body else ""
        title = re.sub(r"\s#\w+", "", first).strip() or post.key.rsplit("/", 1)[-1].replace("-", " ")
    options = {k: v for k, v in pcfg.items()}
    options.update({k: v for k, v in ov.items() if k not in ("text", "title", "link", "hashtags")})
    return Rendered(platform, post, text, title, link, options)


def text_length(text: str, platform: str) -> int:
    if platform == "x":  # X counts every URL as 23 characters
        return len(_URL.sub("x" * 23, text))
    return len(text)


def _fit(body: str, tail: str, limit: int, platform: str) -> str:
    joined = "\n\n".join(p for p in (body, tail) if p)
    if text_length(joined, platform) <= limit:
        return joined
    if tail and text_length(tail, platform) > limit // 2:
        tail = ""  # drop hashtags/link rather than gut the message
    room = limit - text_length(tail, platform) - (2 if tail else 0) - 1
    cut = body[: max(room, 0)]
    if " " in cut[room // 2:]:
        cut = cut[: cut.rfind(" ")]
    cut = cut.rstrip(" ,.;:-\n") + "…"
    return "\n\n".join(p for p in (cut, tail) if p)


def _list(value) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v).strip() for v in value]


def _hashtags(value) -> list[str]:
    tags = []
    for t in _list(value) if not isinstance(value, str) else value.replace(",", " ").split():
        t = re.sub(r"[^\w]", "", t.lstrip("#"))
        if t and t.lower() not in (x.lower() for x in tags):
            tags.append(t)
    return tags
