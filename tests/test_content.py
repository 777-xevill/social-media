from datetime import datetime

import pytest

from bot.content import ContentError, load_posts, parse_post, render, text_length
from bot.platforms.linkedin import little_text


def write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_markdown_post(tmp_path, cfg):
    path = write(tmp_path, "hello.md", """---
media: [clip.mp4]
hashtags: [one, "#two", three]
publish_at: 2026-11-05 19:00
x: Short version
pinterest:
  link: https://example.com
---
The caption body.
""")
    post = parse_post(path, cfg.tz, tmp_path)
    assert post.key == "hello"
    assert post.text == "The caption body."
    assert post.hashtags == ["one", "two", "three"]
    assert post.kind == "video"
    assert post.publish_at == datetime(2026, 11, 5, 19, 0, tzinfo=cfg.tz)
    assert post.overrides["x"] == {"text": "Short version"}
    assert post.overrides["pinterest"]["link"] == "https://example.com"


def test_rejects_unknown_platform(tmp_path, cfg):
    path = write(tmp_path, "bad.md", "---\nplatforms: [myspace]\n---\nhi\n")
    with pytest.raises(ContentError):
        parse_post(path, cfg.tz, tmp_path)


def test_examples_are_ignored_and_errors_collected(tmp_path, cfg):
    posts_dir = tmp_path / "posts"
    posts_dir.mkdir()
    write(posts_dir, "_example.md", "---\nplatforms: [nope]\n---\nhi\n")
    write(posts_dir, "good.md", "hi there")
    write(posts_dir, "broken.md", "---\nvideo_format: medium\n---\nhi\n")
    posts, errors = load_posts(cfg.tz, posts_dir)
    assert list(posts) == ["good"]
    assert len(errors) == 1 and "broken" in errors[0]


def test_x_text_is_shortened_and_counts_urls_as_23(tmp_path, cfg):
    long = "word " * 100
    path = write(tmp_path, "long.md", f"---\nlink: https://example.com/{'a' * 80}\nhashtags: [a, b, c]\n---\n{long}")
    post = parse_post(path, cfg.tz, tmp_path)
    r = render(post, "x", cfg.platform("x"))
    assert text_length(r.text, "x") <= 280
    assert r.text.count("#") == 2  # max_hashtags for x
    assert "https://example.com/" in r.text
    assert "…" in r.text


def test_link_card_platforms_keep_link_out_of_text_posts(tmp_path, cfg):
    path = write(tmp_path, "l.md", "---\nlink: https://example.com\n---\nRead this")
    post = parse_post(path, cfg.tz, tmp_path)
    assert "https://example.com" not in render(post, "facebook", cfg.platform("facebook")).text
    assert "https://example.com" in render(post, "x", cfg.platform("x")).text


def test_title_falls_back_to_first_line(tmp_path, cfg):
    path = write(tmp_path, "t.md", "First line here #tag\nSecond line")
    post = parse_post(path, cfg.tz, tmp_path)
    assert render(post, "youtube", {}).title == "First line here"


def test_linkedin_escaping():
    assert little_text("Hi (there) #growth") == "Hi \\(there\\) {hashtag|\\#|growth}"
