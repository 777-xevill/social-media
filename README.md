# Social Autopilot

Your personal social media manager. Drop posts into a folder once and they go out on
schedule to Facebook, Instagram, Threads, YouTube, TikTok, LinkedIn, X and Pinterest.
It runs on GitHub's servers, so your computer can stay off for weeks.

**Cost: $0.** Only free tiers are used: GitHub Actions, GitHub Pages and each platform's free API.
X and TikTok go through Buffer's free plan.

## How it works

```
 you ──push──▶ GitHub repo ──every 15 min──▶ GitHub Actions runs the bot
               content/posts/*.md                    │
               content/media/*.mp4                   ├─▶ Facebook, Instagram, Threads   (Meta APIs)
                     │                               ├─▶ YouTube                         (YouTube Data API)
                     └─▶ GitHub Pages serves media ──┤─▶ LinkedIn, Pinterest             (their APIs)
                         (Instagram/Threads/Buffer   └─▶ X, TikTok                       (Buffer free API)
                          download from here)
                                                     ✉ problems → GitHub issue → email to you
```

- **Queue mode:** posts without a date take the next free slot (default: 10:00 and 19:00 every day, Dhaka time).
- **Fixed dates:** `publish_at: 2026-11-05 19:00` posts at exactly that time.
- **Evergreen recycling:** if you stop adding content, the bot re-posts your best
  `evergreen: true` posts (each at most once every 45 days) so your accounts never go quiet.
- **Self-healing:** each platform is retried 3 times independently. Missed slots after downtime are
  re-scheduled, not dumped all at once. Posts on the same platform are spaced at least 60 min apart.
- **You hear about problems by email:** failures, expiring tokens and a low queue open a
  GitHub issue, and GitHub emails it to you. A weekly health check covers every account.

## Platform status (October 2026)

| Platform | Route | Fully automatic? | Notes |
|---|---|---|---|
| Facebook Page | Graph API | ✅ Yes | Page token never expires. Facebook **Groups** can't be automated (Meta removed that API in 2024). |
| Instagram | Graph API via your Page | ✅ Yes | Needs a Business/Creator account linked to the Page. Images must be `.jpg`. |
| Threads | Threads API | ✅ Yes | 60-day token, renewed by the bot automatically. |
| YouTube | Data API | ✅ After a free audit | Until Google audits your API project, uploads are forced **private**. Meanwhile you can route YouTube through Buffer. |
| TikTok | Buffer free plan | ✅ Yes | TikTok's own API only allows private posts for personal apps. |
| X | Buffer free plan | ✅ Yes | X's own API has been pay-per-post since Feb 2026. Buffer is the free route. |
| LinkedIn | Share on LinkedIn | ⚠ Almost | LinkedIn gives personal apps 60-day tokens with no auto-renewal. The bot emails you 2 weeks before expiry. Renewing takes 2 minutes. |
| Pinterest | API v5 | ✅ After approval | Free "Standard access" needs a short demo video. Until then pins are hidden (sandbox). |
| Reddit | Reddit API | ⏳ If approved | Since Nov 2025 Reddit approves API access by hand. Off by default. Subreddits also ban automated self-promotion, so post to your own profile. |
| Snapchat | — | ❌ No | No public posting API. Optional: the bot emails you the file and caption to post by hand. |

Buffer's free plan allows 3 channels: X, TikTok, and one spare (YouTube or Pinterest while their approvals are pending).

## Everyday use

Add a post and you're done. See [content/README.md](content/README.md) for every option.

```markdown
---
media: [my-reel.mp4]
title: 3 automations that save me 10 hours a week
hashtags: [automation, productivity, founders]
evergreen: true
---
3 automations that save me 10 hours every week 👇 …
```

You can upload files on github.com (Add file → Upload files) or push with git.

| Command | What it does |
|---|---|
| `python -m bot new "Post title"` | Create a new post file from the template |
| `python -m bot plan` | Show the upcoming schedule |
| `python -m bot validate` | Check your posts for mistakes |
| `python -m bot run --dry-run --now 2026-11-05T19:05` | Show what would be posted at that time, without posting |
| `python -m bot auth <meta\|threads\|youtube\|linkedin\|pinterest\|buffer\|reddit>` | Connect an account |
| `python -m bot secrets` | Upload your connected accounts to GitHub |
| `python -m bot health` | Check every connected account |

On GitHub you can also go to **Actions → Publish → Run workflow** to post right away.

## Setup

One-time, about 1–2 hours in total, and you can connect platforms one at a time.
Unconnected platforms are simply skipped. → **[SETUP.md](SETUP.md)**

## Why the repo is public

A free GitHub account gets unlimited Actions minutes and GitHub Pages only for public repos,
and Pages is what lets Instagram, Threads and Buffer download your videos. Your tokens stay secret:
they're stored in GitHub Secrets, and the few the bot renews are encrypted. The trade-off: anyone
browsing the repo can see posts *before* they go live.

## Files

```
config.yaml          schedule, timezone, which platforms are on
content/posts/       your posts (.md or .yaml). Files starting with _ are examples.
content/media/       photos and videos
bot/                 the bot (Python)
site/                privacy policy, terms and OAuth page (needed by the developer apps)
state/               what was posted. Updated by the bot, don't edit.
.github/workflows/   publish (every 15 min), health (weekly), validate (on every push)
```
