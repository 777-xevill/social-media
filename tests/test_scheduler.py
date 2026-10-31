from datetime import datetime, timedelta
from pathlib import Path

from bot import scheduler
from bot.content import Post
from bot.state import iso, parse_iso


def post(key, **kw):
    return Post(key=key, path=Path(f"{key}.md"), text=kw.pop("text", "hello"), **kw)


def new_state():
    return {"posts": {}, "platform_last": {}, "last_tick": None}


def local(cfg, *args):
    return datetime(*args, tzinfo=cfg.tz)


def dues(state, key, cfg):
    return [parse_iso(r["due"]).astimezone(cfg.tz) for r in state["posts"][key]["runs"]]


def test_queue_takes_consecutive_slots_in_filename_order(cfg):
    now = local(cfg, 2026, 11, 2, 9, 0)
    state = new_state()
    posts = {k: post(k) for k in ["b-second", "a-first", "c-third"]}
    scheduler.plan(state, posts, cfg, now)
    assert dues(state, "a-first", cfg) == [local(cfg, 2026, 11, 2, 10, 0)]
    assert dues(state, "b-second", cfg) == [local(cfg, 2026, 11, 2, 19, 0)]
    assert dues(state, "c-third", cfg) == [local(cfg, 2026, 11, 3, 10, 0)]


def test_new_queue_post_goes_after_existing_queue(cfg):
    now = local(cfg, 2026, 11, 2, 9, 0)
    state = new_state()
    posts = {"a": post("a"), "b": post("b")}
    scheduler.plan(state, posts, cfg, now)
    posts["0-late-but-early-name"] = post("0-late-but-early-name")
    scheduler.plan(state, posts, cfg, now + timedelta(minutes=15))
    assert dues(state, "0-late-but-early-name", cfg) == [local(cfg, 2026, 11, 3, 10, 0)]


def test_fixed_date_post_and_slot_collision(cfg):
    now = local(cfg, 2026, 11, 2, 9, 0)
    state = new_state()
    posts = {"fixed": post("fixed", publish_at=local(cfg, 2026, 11, 2, 10, 30)), "q": post("q")}
    scheduler.plan(state, posts, cfg, now)
    assert dues(state, "fixed", cfg) == [local(cfg, 2026, 11, 2, 10, 30)]
    # 10:00 is within 60 min of the fixed post, so the queue post takes 19:00
    assert dues(state, "q", cfg) == [local(cfg, 2026, 11, 2, 19, 0)]


def test_editing_publish_at_moves_unstarted_run(cfg):
    now = local(cfg, 2026, 11, 2, 9, 0)
    state = new_state()
    posts = {"p": post("p", publish_at=local(cfg, 2026, 11, 5, 10, 0))}
    scheduler.plan(state, posts, cfg, now)
    posts["p"].publish_at = local(cfg, 2026, 11, 6, 12, 0)
    scheduler.plan(state, posts, cfg, now)
    assert dues(state, "p", cfg) == [local(cfg, 2026, 11, 6, 12, 0)]


def test_offline_bot_reslots_queue_in_order(cfg):
    state = new_state()
    posts = {k: post(k) for k in ["a", "b", "c"]}
    scheduler.plan(state, posts, cfg, local(cfg, 2026, 11, 2, 9, 0))
    back = local(cfg, 2026, 11, 10, 12, 0)  # bot was down for a week
    scheduler.plan(state, posts, cfg, back)
    assert dues(state, "a", cfg) == [local(cfg, 2026, 11, 10, 19, 0)]
    assert dues(state, "b", cfg) == [local(cfg, 2026, 11, 11, 10, 0)]
    assert dues(state, "c", cfg) == [local(cfg, 2026, 11, 11, 19, 0)]


def test_deleted_unstarted_post_is_forgotten(cfg):
    state = new_state()
    posts = {"a": post("a")}
    scheduler.plan(state, posts, cfg, local(cfg, 2026, 11, 2, 9, 0))
    scheduler.plan(state, {}, cfg, local(cfg, 2026, 11, 2, 9, 15))
    assert state["posts"] == {}


def _published(state, key):
    for run in state["posts"][key]["runs"]:
        run["platforms"] = {"facebook": {"status": "published"}}
        run["done"] = True


def test_evergreen_recycles_when_idle(cfg):
    state = new_state()
    posts = {"green": post("green", evergreen=True), "plain": post("plain")}
    scheduler.plan(state, posts, cfg, local(cfg, 2026, 9, 1, 9, 0))
    _published(state, "green")
    _published(state, "plain")

    tick = local(cfg, 2026, 11, 2, 10, 7)  # just after the 10:00 slot, nothing posted for 2 months
    state["last_tick"] = iso(tick - timedelta(minutes=15))
    notes = scheduler.plan(state, posts, cfg, tick)
    assert any("evergreen" in n for n in notes)
    assert dues(state, "green", cfg)[-1] == local(cfg, 2026, 11, 2, 10, 0)
    assert len(state["posts"]["plain"]["runs"]) == 1


def test_evergreen_waits_while_queue_is_busy(cfg):
    state = new_state()
    posts = {"green": post("green", evergreen=True)}
    scheduler.plan(state, posts, cfg, local(cfg, 2026, 9, 1, 9, 0))
    _published(state, "green")
    posts["fresh"] = post("fresh", publish_at=local(cfg, 2026, 11, 2, 15, 0))
    tick = local(cfg, 2026, 11, 2, 10, 7)
    state["last_tick"] = iso(tick - timedelta(minutes=15))
    scheduler.plan(state, posts, cfg, tick)
    assert len(state["posts"]["green"]["runs"]) == 1


def test_evergreen_respects_min_days(cfg):
    state = new_state()
    posts = {"green": post("green", evergreen=True)}
    scheduler.plan(state, posts, cfg, local(cfg, 2026, 10, 20, 9, 0))
    _published(state, "green")
    tick = local(cfg, 2026, 11, 2, 10, 7)  # only ~13 days later
    state["last_tick"] = iso(tick - timedelta(minutes=15))
    scheduler.plan(state, posts, cfg, tick)
    assert len(state["posts"]["green"]["runs"]) == 1


def test_due_runs(cfg):
    state = new_state()
    posts = {"a": post("a"), "b": post("b")}
    now = local(cfg, 2026, 11, 2, 9, 0)
    scheduler.plan(state, posts, cfg, now)
    assert scheduler.due_runs(state, now) == []
    later = local(cfg, 2026, 11, 2, 10, 5)
    assert [k for k, _ in scheduler.due_runs(state, later)] == ["a"]
