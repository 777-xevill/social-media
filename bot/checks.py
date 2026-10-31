"""`validate` (content sanity check on every push) and `health` (weekly credential check)."""
from __future__ import annotations

from datetime import timedelta

from . import scheduler
from .config import MEDIA_DIR, PLATFORMS, Config
from .content import IMAGE_EXT, VIDEO_EXT, load_posts, render
from .net import ApiError, log
from .platforms import Context, build
from .platforms.linkedin import LinkedIn
from .platforms.others import Unsupported
from .state import State, iso, utcnow

GITHUB_FILE_LIMIT = 100 * 1024 * 1024


def validate(ctx: Context) -> tuple[list[str], list[str]]:
    cfg = ctx.cfg
    posts, errors = load_posts(cfg.tz)
    warnings: list[str] = []
    if not cfg.site_url:
        errors.append("config.yaml: site_url is empty")
    if not cfg.slots:
        warnings.append("config.yaml: no schedule slots — posts without publish_at will never go out")
    for name in (cfg.raw.get("platforms") or {}):
        if name not in PLATFORMS:
            errors.append(f"config.yaml: unknown platform '{name}'")
    for name in cfg.default_platforms:
        if name not in PLATFORMS:
            errors.append(f"config.yaml: unknown platform '{name}' in default_platforms")

    adapters = build(ctx)
    state = State()
    now = utcnow()
    for key, post in posts.items():
        for rel in post.media:
            path = MEDIA_DIR / rel
            if not path.is_file():
                errors.append(f"{key}: media file not found: content/media/{rel}")
                continue
            if path.suffix.lower() not in IMAGE_EXT | VIDEO_EXT:
                errors.append(f"{key}: unsupported media type {path.suffix} ({rel})")
            if path.stat().st_size > GITHUB_FILE_LIMIT:
                errors.append(f"{key}: {rel} is over GitHub's 100 MB file limit — compress it")
        if post.publish_at and post.publish_at < now and key not in state.posts:
            warnings.append(f"{key}: publish_at is in the past — it will go out on the next run")
        for name in post.targets(cfg.default_platforms):
            pcfg = cfg.platform(name)
            if not pcfg["enabled"] or isinstance(adapters[name], Unsupported):
                continue
            r = render(post, name, pcfg)
            reason = adapters[name].incompatible(r)
            # Only nag about format mismatches (e.g. text post → YouTube) if the post asked for that platform.
            mismatch = post.kind not in adapters[name].supports
            if reason and not (mismatch and post.platforms is None):
                warnings.append(f"{key}: won't go to {name} — {reason}")
            body = post.overrides.get(name, {}).get("text", post.text)
            if r.text.endswith("…") and not str(body).endswith("…"):
                warnings.append(f"{key}: text is too long for {name} and will be shortened "
                                f"— add a `{name}:` version to control it")
    return errors, warnings


def health(ctx: Context) -> tuple[list[str], list[str]]:
    """Returns (report lines, problems). Also refreshes rotating tokens and keeps workflows alive."""
    cfg, now = ctx.cfg, utcnow()
    adapters = build(ctx)
    report, problems = ["| Platform | Status |", "|---|---|"], []
    for name in PLATFORMS:
        pcfg, adapter = cfg.platform(name), adapters[name]
        via = f" (via {pcfg['via']})" if pcfg["via"] != "direct" else ""
        if not pcfg["enabled"]:
            report.append(f"| {name} | off |")
            continue
        missing = adapter.missing_secrets()
        if isinstance(adapter, Unsupported):
            report.append(f"| {name} | ⚠ {adapter.REASONS.get(name, 'unsupported')} |")
            continue
        if missing:
            report.append(f"| {name}{via} | not connected yet — {adapter.setup_hint} |")
            continue
        try:
            info = adapter.health()
            if isinstance(adapter, LinkedIn):
                expires = adapter.expires_at()
                if expires:
                    info += f", token expires {expires:%d %b %Y}"
                    if expires - now < timedelta(days=14):
                        problems.append(f"LinkedIn token expires {expires:%d %b %Y} — {adapter.setup_hint}, "
                                        "then `python -m bot secrets`")
            report.append(f"| {name}{via} | ✅ {info} |")
        except Exception as e:
            msg = str(e) if isinstance(e, ApiError) else f"{type(e).__name__}: {e}"
            report.append(f"| {name}{via} | ❌ {msg} |")
            problems.append(f"{name}: {msg} — {adapter.setup_hint}")

    posts, errors = load_posts(cfg.tz)
    state = State()
    queued = sum(1 for k, r in scheduler.upcoming(state.data, now) if r["kind"] != "evergreen")
    queued += sum(1 for k, p in posts.items() if not state.posts.get(k, {}).get("runs"))
    report.append(f"\n**Queue:** {queued} upcoming post(s). "
                  f"**Evergreen:** {sum(p.evergreen for p in posts.values())} post(s) available for recycling.")
    if queued < int(cfg.posting["low_queue_warning"]):
        problems.append(f"only {queued} new post(s) left in the queue — add more to content/posts/"
                        + (" (evergreen posts will keep the accounts active meanwhile)" if cfg.evergreen["enabled"] else ""))
    problems += [f"invalid post file: {e}" for e in errors]

    state.data["heartbeat"] = iso(now)  # a commit every week keeps the repo "active" for GitHub
    state.save()
    ctx.tokens.save()
    ctx.github.enable_workflows(["publish.yml", "health.yml"])
    if problems:
        body = ("Weekly check found something that needs you:\n\n" + "\n".join(f"- {p}" for p in problems)
                + "\n\n<details><summary>Full report</summary>\n\n" + "\n".join(report) + "\n</details>")
        ctx.github.alert("🩺 Social Autopilot needs attention", body)
    for line in report:
        log(line)
    return report, problems
