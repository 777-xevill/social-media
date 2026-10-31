"""Decides when each post goes out: fixed dates, queue slots and evergreen re-posts.

Every post gets one or more "runs" in state. A run has a due time and a status per
platform. Queue posts get the next free slot the first time the bot sees them.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterator

from .config import Config
from .content import Post
from .state import iso, parse_iso

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
STALE_AFTER = timedelta(hours=6)   # untouched queue runs this late are re-slotted


def next_slots(cfg: Config, after: datetime) -> Iterator[datetime]:
    """Slot times strictly after `after`, in order."""
    slots = []
    for rule in cfg.slots:
        days = [d.lower()[:3] for d in rule.get("days") or DAYS]
        for t in rule.get("times") or []:
            hh, mm = (int(x) for x in str(t).split(":"))
            slots.extend((DAYS.index(d), hh, mm) for d in days)
    if not slots:
        return
    day = after.astimezone(cfg.tz).date()
    for _ in range(800):
        todays = sorted({(h, m) for wd, h, m in slots if wd == day.weekday()})
        for h, m in todays:
            dt = datetime(day.year, day.month, day.day, h, m, tzinfo=cfg.tz)
            if dt > after:
                yield dt
        day += timedelta(days=1)


def _new_run(due: datetime, kind: str, now: datetime) -> dict:
    return {"due": iso(due), "kind": kind, "created": iso(now), "platforms": {}}


def _all_runs(state: dict):
    for key, entry in state["posts"].items():
        for run in entry["runs"]:
            yield key, run


def plan(state: dict, posts: dict[str, Post], cfg: Config, now: datetime) -> list[str]:
    """Creates/updates runs for this tick. Returns human-readable notes."""
    notes: list[str] = []
    gap = timedelta(minutes=int(cfg.posting["min_minutes_between_posts"]))

    # 0. Post files that were deleted: forget runs that never started.
    for key in [k for k in state["posts"] if k not in posts]:
        runs = [r for r in state["posts"][key]["runs"] if r["platforms"]]
        if runs:
            state["posts"][key]["runs"] = runs
        else:
            del state["posts"][key]

    # 1. Posts with a fixed date: create the run, or follow edits until it starts.
    for key, post in posts.items():
        runs = state["posts"].setdefault(key, {"runs": []})["runs"]
        last = runs[-1] if runs else None
        untouched = last is not None and not last["platforms"] and last["kind"] != "evergreen"
        if post.publish_at:
            if not runs:
                runs.append(_new_run(post.publish_at, "scheduled", now))
                notes.append(f"scheduled {key} for {post.publish_at.astimezone(cfg.tz):%a %d %b %H:%M}")
            elif untouched and (last["due"] != iso(post.publish_at) or last["kind"] != "scheduled"):
                last.update(due=iso(post.publish_at), kind="scheduled")
                notes.append(f"moved {key} to {post.publish_at.astimezone(cfg.tz):%a %d %b %H:%M}")
        elif untouched and last["kind"] == "scheduled":
            runs.pop()  # date removed → goes back into the queue below

    # 2. Queue posts. Re-slot everything (keeping order) if the bot missed slots.
    pending_queue = [r for _, r in _all_runs(state) if r["kind"] == "queue" and not r["platforms"]]
    pending_ids = {id(r) for r in pending_queue}
    taken = [parse_iso(r["due"]) for _, r in _all_runs(state) if id(r) not in pending_ids]

    def next_free(cursor: datetime) -> datetime | None:
        for slot in next_slots(cfg, cursor):
            if all(abs(slot - t) >= gap for t in taken):
                return slot
        return None

    if any(parse_iso(r["due"]) < now - STALE_AFTER for r in pending_queue):
        cursor = now
        for run in sorted(pending_queue, key=lambda r: r["due"]):
            slot = next_free(cursor)
            if slot:
                run["due"] = iso(slot)
                taken.append(slot)
                cursor = slot
        notes.append(f"bot was offline — re-slotted {len(pending_queue)} queued post(s)")
    else:
        taken += [parse_iso(r["due"]) for r in pending_queue]
        cursor = max([now] + [parse_iso(r["due"]) for _, r in _all_runs(state) if r["kind"] == "queue"])

    for key in sorted(posts):
        post = posts[key]
        entry = state["posts"].setdefault(key, {"runs": []})
        if post.publish_at or entry["runs"]:
            continue
        slot = next_free(cursor)
        if slot is None:
            notes.append(f"no schedule slots configured — {key} can't be queued")
            continue
        entry["runs"].append(_new_run(slot, "queue", now))
        taken.append(slot)
        cursor = slot
        notes.append(f"queued {key} for {slot:%a %d %b %H:%M}")

    # 3. Evergreen: drop missed re-posts, then fill an idle slot.
    for _, entry in state["posts"].items():
        entry["runs"] = [r for r in entry["runs"] if not (
            r["kind"] == "evergreen" and not r["platforms"] and parse_iso(r["due"]) < now - STALE_AFTER)]

    eg = cfg.evergreen
    if eg["enabled"]:
        last_tick = parse_iso(state.get("last_tick")) or now - timedelta(minutes=20)
        elapsed = [s for s in _until(next_slots(cfg, last_tick), now)]
        window = timedelta(hours=float(eg["idle_hours"]))
        busy = any(abs(parse_iso(r["due"]) - now) < window for _, r in _all_runs(state))
        if elapsed and not busy:
            pick = _pick_evergreen(state, posts, now - timedelta(days=float(eg["min_days_between_reposts"])))
            if pick:
                state["posts"][pick]["runs"].append(_new_run(elapsed[-1], "evergreen", now))
                notes.append(f"nothing new to post — recycling evergreen post {pick}")
    return notes


def _until(it: Iterator[datetime], end: datetime):
    for dt in it:
        if dt > end:
            return
        yield dt


def _pick_evergreen(state: dict, posts: dict[str, Post], cutoff: datetime) -> str | None:
    best, best_due = None, None
    for key, post in posts.items():
        runs = state["posts"].get(key, {}).get("runs", [])
        if not post.evergreen or not runs:
            continue
        if not any(p.get("status") == "published" for r in runs for p in r["platforms"].values()):
            continue  # never published yet
        last_due = max(parse_iso(r["due"]) for r in runs)
        if last_due < cutoff and (best_due is None or last_due < best_due):
            best, best_due = key, last_due
    return best


def due_runs(state: dict, now: datetime) -> list[tuple[str, dict]]:
    runs = [(k, r) for k, r in _all_runs(state) if not r.get("done") and parse_iso(r["due"]) <= now]
    return sorted(runs, key=lambda kr: kr[1]["due"])


def upcoming(state: dict, now: datetime) -> list[tuple[str, dict]]:
    runs = [(k, r) for k, r in _all_runs(state) if not r.get("done") and parse_iso(r["due"]) > now]
    return sorted(runs, key=lambda kr: kr[1]["due"])
