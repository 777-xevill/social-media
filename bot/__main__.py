"""Command line: `python -m bot <command>`. Run `python -m bot -h` for the list."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta

from .config import POSTS_DIR, Config
from .state import utcnow

TEMPLATE = """---
# Leave publish_at out to use the next free slot from config.yaml.
# publish_at: {when}
# platforms: [instagram, facebook, youtube, tiktok, threads, linkedin, x, pinterest]
media: []            # files in content/media/, e.g. [my-video.mp4]
title: {title}
hashtags: []
evergreen: false     # true = may be re-posted later when the queue runs dry
---
Write the caption here.
"""


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="python -m bot", description="Social Autopilot")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="post everything that is due (what GitHub Actions runs)")
    r.add_argument("--dry-run", action="store_true", help="show what would be posted, change nothing")
    r.add_argument("--now", help="pretend it is this time (ISO, for testing with --dry-run)")
    pl = sub.add_parser("plan", help="show the upcoming schedule")
    pl.add_argument("--days", type=int, default=14)
    sub.add_parser("validate", help="check posts and config for mistakes")
    sub.add_parser("health", help="check every connected account (weekly in Actions)")
    a = sub.add_parser("auth", help="connect an account (run on your computer)")
    a.add_argument("platform", choices=["meta", "threads", "youtube", "linkedin", "pinterest", "buffer", "reddit"])
    sub.add_parser("secrets", help="upload .env to GitHub Secrets")
    n = sub.add_parser("new", help="create a new post file from the template")
    n.add_argument("title")
    args = p.parse_args(argv)

    if args.cmd == "auth":
        from .auth import run
        run(args.platform)
        return 0
    if args.cmd == "secrets":
        from .auth import push_secrets
        push_secrets()
        return 0
    if args.cmd == "new":
        slug = re.sub(r"[^a-z0-9]+", "-", args.title.lower()).strip("-") or "post"
        path = POSTS_DIR / f"{utcnow():%Y-%m-%d}-{slug}.md"
        if path.exists():
            raise SystemExit(f"{path} already exists")
        when = (datetime.now(Config().tz) + timedelta(days=1)).strftime("%Y-%m-%d 10:00")
        POSTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(TEMPLATE.format(when=when, title=args.title), encoding="utf-8")
        print(f"Created {path}")
        return 0

    from .publisher import make_context, tick
    ctx = make_context()

    if args.cmd == "run":
        now = None
        if args.now:
            now = datetime.fromisoformat(args.now)
            now = now.replace(tzinfo=ctx.cfg.tz) if now.tzinfo is None else now
        lines = tick(ctx, now=now, dry_run=args.dry_run)
        print("\n".join(lines) if lines else "Nothing due right now.")
        return 0

    if args.cmd == "plan":
        from . import scheduler
        from .content import load_posts
        from .state import State, parse_iso
        posts, errors = load_posts(ctx.cfg.tz)
        state = State()
        now = utcnow()
        scheduler.plan(state.data, posts, ctx.cfg, now)  # preview only — not saved
        end = now + timedelta(days=args.days)
        rows = [(k, r) for k, r in scheduler.upcoming(state.data, now) if parse_iso(r["due"]) <= end]
        for k, r in scheduler.due_runs(state.data, now):
            print(f"  DUE NOW            {k}")
        for k, r in rows:
            when = parse_iso(r["due"]).astimezone(ctx.cfg.tz)
            post = posts.get(k)
            targets = ", ".join(post.targets(ctx.cfg.default_platforms)) if post else "?"
            print(f"  {when:%a %d %b %H:%M}   {k}  [{r['kind']}] → {targets}")
        if not rows:
            print("Nothing scheduled in that window.")
        for e in errors:
            print(f"✖ {e}")
        return 1 if errors else 0

    if args.cmd == "validate":
        from .checks import validate
        errors, warnings = validate(ctx)
        for w in warnings:
            print(f"⚠ {w}")
        for e in errors:
            print(f"✖ {e}")
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s).")
        return 1 if errors else 0

    if args.cmd == "health":
        from .checks import health
        health(ctx)  # problems are reported by issue (email), not by failing the job
    return 0


if __name__ == "__main__":
    sys.exit(main())
