from datetime import datetime, timedelta
from pathlib import Path

import pytest

from bot import publisher
from bot.content import Post
from bot.github import GitHub
from bot.net import ApiError, NotReady
from bot.platforms import Context
from bot.platforms.base import Adapter
from bot.state import State, TokenStore


class Fake(Adapter):
    def __init__(self, ctx, name, behaviour):
        self.name = name
        super().__init__(ctx)
        self.behaviour, self.calls = behaviour, 0

    def publish(self, r):
        self.calls += 1
        b = self.behaviour.pop(0) if isinstance(self.behaviour, list) else self.behaviour
        if b == "ok":
            return {"id": f"{self.name}-1", "url": f"https://{self.name}.example/1"}
        if b == "notready":
            raise NotReady("pages not live")
        raise ApiError(self.name, "boom")


@pytest.fixture
def env(tmp_path, cfg, monkeypatch):
    class Secrets:
        def missing(self, *k):
            return []

        def get(self, k, d=None):
            return d

    ctx = Context(cfg, Secrets(), TokenStore(None, tmp_path / "t.enc"), GitHub(token="", repo=""))
    posts = {"a": Post(key="a", path=Path("a.md"), text="hello", platforms=["facebook", "x"],
                       publish_at=datetime(2026, 11, 2, 10, 0, tzinfo=cfg.tz))}
    adapters = {}
    alerts = []
    monkeypatch.setattr(publisher, "load_posts", lambda tz: (posts, []))
    monkeypatch.setattr(publisher, "State", lambda: State(tmp_path / "state.json"))
    monkeypatch.setattr(publisher, "build", lambda ctx: adapters)
    monkeypatch.setattr(GitHub, "alert", lambda self, title, body, label="": alerts.append(body))
    return ctx, posts, adapters, alerts, tmp_path


def at(cfg, h, m=0, day=2):
    return datetime(2026, 11, day, h, m, tzinfo=cfg.tz)


def test_publishes_due_post_once(env, cfg):
    ctx, posts, adapters, alerts, tmp = env
    adapters.update(facebook=Fake(ctx, "facebook", "ok"), x=Fake(ctx, "x", "ok"))
    assert publisher.tick(ctx, now=at(cfg, 9, 50)) == []
    lines = publisher.tick(ctx, now=at(cfg, 10, 5))
    assert len(lines) == 2
    publisher.tick(ctx, now=at(cfg, 10, 20))
    assert adapters["facebook"].calls == 1 and adapters["x"].calls == 1
    run = State(tmp / "state.json").posts["a"]["runs"][0]
    assert run["done"] and run["platforms"]["x"]["url"] == "https://x.example/1"


def test_one_platform_failing_does_not_block_others_and_alerts_after_retries(env, cfg):
    ctx, posts, adapters, alerts, tmp = env
    adapters.update(facebook=Fake(ctx, "facebook", "ok"), x=Fake(ctx, "x", "fail"))
    publisher.tick(ctx, now=at(cfg, 10, 5))
    assert adapters["facebook"].calls == 1 and adapters["x"].calls == 1
    publisher.tick(ctx, now=at(cfg, 10, 10))          # retry not due yet (20 min backoff)
    assert adapters["x"].calls == 1
    publisher.tick(ctx, now=at(cfg, 10, 30))          # attempt 2
    publisher.tick(ctx, now=at(cfg, 11, 20))          # attempt 3 → failed
    assert adapters["x"].calls == 3 and len(alerts) == 1
    run = State(tmp / "state.json").posts["a"]["runs"][0]
    assert run["platforms"]["x"]["status"] == "failed" and run["done"]
    publisher.tick(ctx, now=at(cfg, 13, 0))
    assert adapters["x"].calls == 3 and adapters["facebook"].calls == 1


def test_not_ready_waits_without_counting_an_attempt(env, cfg):
    ctx, posts, adapters, alerts, tmp = env
    adapters.update(facebook=Fake(ctx, "facebook", "ok"), x=Fake(ctx, "x", ["notready", "ok"]))
    publisher.tick(ctx, now=at(cfg, 10, 5))
    run = State(tmp / "state.json").posts["a"]["runs"][0]
    assert "x" not in run["platforms"]
    publisher.tick(ctx, now=at(cfg, 10, 20))
    run = State(tmp / "state.json").posts["a"]["runs"][0]
    assert run["platforms"]["x"]["status"] == "published" and not alerts


def test_spacing_between_posts_on_same_platform(env, cfg):
    ctx, posts, adapters, alerts, tmp = env
    posts["b"] = Post(key="b", path=Path("b.md"), text="second", platforms=["facebook"],
                      publish_at=datetime(2026, 11, 2, 10, 0, tzinfo=cfg.tz))
    adapters.update(facebook=Fake(ctx, "facebook", "ok"), x=Fake(ctx, "x", "ok"))
    publisher.tick(ctx, now=at(cfg, 10, 5))
    assert adapters["facebook"].calls == 1                 # second post held back
    publisher.tick(ctx, now=at(cfg, 10, 50))
    assert adapters["facebook"].calls == 1
    publisher.tick(ctx, now=at(cfg, 11, 6))
    assert adapters["facebook"].calls == 2


def test_disabled_and_unconnected_platforms_are_skipped(env, cfg, monkeypatch):
    ctx, posts, adapters, alerts, tmp = env
    fb, x = Fake(ctx, "facebook", "ok"), Fake(ctx, "x", "ok")
    monkeypatch.setattr(x, "missing_secrets", lambda: ["BUFFER_API_KEY"])
    adapters.update(facebook=fb, x=x)
    publisher.tick(ctx, now=at(cfg, 10, 5))
    run = State(tmp / "state.json").posts["a"]["runs"][0]
    assert run["platforms"]["x"]["status"] == "skipped" and "BUFFER_API_KEY" in run["platforms"]["x"]["reason"]
    assert x.calls == 0 and run["done"]


def test_dry_run_changes_nothing(env, cfg):
    ctx, posts, adapters, alerts, tmp = env
    adapters.update(facebook=Fake(ctx, "facebook", "ok"), x=Fake(ctx, "x", "ok"))
    adapters["x"].missing_secrets = lambda: ["BUFFER_API_KEY"]
    lines = publisher.tick(ctx, now=at(cfg, 10, 5), dry_run=True)
    assert lines[0].startswith("WOULD POST a → facebook") and lines[1].startswith("SKIP a → x")
    assert adapters["facebook"].calls == 0
    assert not (tmp / "state.json").exists()
