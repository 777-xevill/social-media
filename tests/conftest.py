import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(textwrap.dedent("""
        site_url: https://example.github.io/repo
        timezone: Asia/Dhaka
        schedule:
          slots:
            - days: [mon, tue, wed, thu, fri, sat, sun]
              times: ["10:00", "19:00"]
        default_platforms: [facebook, x]
        evergreen: {enabled: true, idle_hours: 24, min_days_between_reposts: 45}
        posting: {min_minutes_between_posts: 60}
        platforms:
          facebook: {enabled: true}
          x: {enabled: true, via: buffer, max_hashtags: 2}
          instagram: {enabled: true, max_hashtags: 5}
    """), encoding="utf-8")
    return Config(path)
