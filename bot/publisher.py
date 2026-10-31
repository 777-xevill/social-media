"""One publishing pass ("tick"): plan the schedule, post what is due, record results."""
from __future__ import annotations

import os
import traceback
from datetime import datetime, timedelta

from . import scheduler
from .config import Config, Secrets
from .content import load_posts, render
from .github import GitHub
from .net import ApiError, NotReady, log, register_secrets
from .platforms import Context, build
from .state import TERMINAL, State, TokenStore, iso, parse_iso, utcnow


def make_context(cfg: Config | None = None) -> Context:
    cfg = cfg or Config()
    secrets = Secrets()
    register_secrets(secrets.sensitive_values())
    return Context(cfg, secrets, TokenStore(secrets.get("TOKEN_STORE_KEY")), GitHub(secrets.get("GITHUB_TOKEN")))


def tick(ctx: Context, now: datetime | None = None, dry_run: bool = False) -> list[str]:
    """Returns a list of summary lines."""
    now = now or utcnow()
    cfg = ctx.cfg
    posts, errors = load_posts(cfg.tz)
    for e in errors:
        log(f"skipping invalid post file — {e}", "error")
    state = State()
    # A dry run with a pretend future `now` still queues posts as of today, so it shows what would go out then.
    plan_now = min(now, utcnow()) if dry_run else now
    for note in scheduler.plan(state.data, posts, cfg, plan_now):
        log(note)

    adapters = build(ctx)
    gap = timedelta(minutes=int(cfg.posting["min_minutes_between_posts"]))
    max_attempts = int(cfg.posting["max_attempts"])
    summary: list[str] = []
    failures: list[tuple[str, str, str, str]] = []

    for key, run in scheduler.due_runs(state.data, now):
        post = posts.get(key)
        if post is None:
            run["done"] = True  # post file was deleted after it started publishing
            continue
        targets = post.targets(cfg.default_platforms)
        for name in targets:
            status = run["platforms"].get(name, {})
            if status.get("status") in TERMINAL:
                continue
            retry_at = parse_iso(status.get("next_at"))
            if retry_at and retry_at > now:
                continue
            adapter, pcfg = adapters[name], cfg.platform(name)

            def mark(**fields):
                run["platforms"][name] = {**fields, "at": iso(now)}
                if dry_run and fields.get("status") == "skipped":
                    summary.append(f"SKIP {key} → {name}: {fields['reason']}")

            if not pcfg["enabled"]:
                mark(status="skipped", reason="turned off in config.yaml")
                continue
            missing = adapter.missing_secrets()
            if missing:
                mark(status="skipped", reason=f"not connected yet (missing {', '.join(missing)})")
                continue
            rendered = render(post, name, pcfg)
            reason = adapter.incompatible(rendered)
            if reason:
                mark(status="skipped", reason=reason)
                continue
            last = parse_iso(state.platform_last.get(name))
            if last and now - last < gap:
                continue  # spacing out posts on this platform — next tick
            if dry_run:
                preview = rendered.text.replace("\n", " ")[:90]
                summary.append(f"WOULD POST {key} → {name}: {preview}")
                continue

            log(f"posting {key} → {name} …")
            try:
                result = adapter.publish(rendered)
            except NotReady as e:
                log(f"{key} → {name}: waiting — {e}")
                continue
            except Exception as e:  # one platform failing must never stop the others
                attempts = int(status.get("attempts", 0)) + 1
                msg = str(e) if isinstance(e, ApiError) else f"{type(e).__name__}: {e}"
                if not isinstance(e, ApiError):
                    log(traceback.format_exc(), "error")
                if attempts >= max_attempts:
                    mark(status="failed", attempts=attempts, error=msg)
                    hint = adapter.setup_hint if isinstance(e, ApiError) and e.auth else ""
                    failures.append((key, name, msg, hint))
                    log(f"{key} → {name} FAILED for good: {msg}", "error")
                else:
                    mark(status="retry", attempts=attempts, error=msg,
                         next_at=iso(now + timedelta(minutes=20 * 2 ** (attempts - 1))))
                    log(f"{key} → {name} failed (attempt {attempts}/{max_attempts}), will retry: {msg}", "warning")
            else:
                mark(status="published", id=result.get("id"), url=result.get("url"))
                state.platform_last[name] = iso(now)
                summary.append(f"✅ {key} → {name}: {result.get('url') or result.get('id')}")
                log(summary[-1])
            state.save()  # record each success immediately so a crash can't cause a double post

        if all(run["platforms"].get(n, {}).get("status") in TERMINAL for n in targets):
            run["done"] = True

    if dry_run:
        return summary
    state.data["last_tick"] = iso(now)
    state.save()
    ctx.tokens.save()

    if failures:
        lines = [f"- **{k}** → `{p}`: {m}" + (f"  \n  ↳ fix: {h}" if h else "") for k, p, m, h in failures]
        ctx.github.alert("🚨 Social Autopilot: some posts failed",
                         f"These posts failed {max_attempts} times and were given up on "
                         f"({now.astimezone(cfg.tz):%d %b %Y %H:%M}):\n\n" + "\n".join(lines) +
                         "\n\nOther platforms were not affected. Close this issue once handled.")
    _step_summary(summary)
    return summary


def _step_summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path and lines:
        with open(path, "a", encoding="utf-8") as f:
            f.write("### Published this run\n\n" + "\n".join(f"- {l}" for l in lines) + "\n")
