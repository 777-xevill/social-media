# Growth plan

What to post and how to judge it. The bot handles posting; this covers the strategy it's missing.

Learned 2026-11-03 from 5 Instagram growth videos. Evidence, timestamps and conflicts: `E:\Brain\wiki\domains\social-growth.md`. Full transcripts: `docs/transcripts/` (local only, ignored by git because this repo is public).

**How far to trust this:** the results are creators' own claims, all five sell courses or coaching, and they cover Instagram only. Using them on other platforms is an assumption. Nothing here has been tested on these accounts.

## Default goal

Xegency sells web design, so the goal is enquiries, not followers. That makes heyDominik's approach the default for this project, because it's the only one of the five built around selling. It's a default, not a settled answer: the sources disagree (see "Open decisions").

## What blocks this today

As of 2026-11-03:

1. **Nothing can post yet.** Accounts aren't connected and Actions runs stop at `action_required` (`HANDOFF.md`).
2. **The first 3 test Reels are queued locally, not committed.** They're in `content/media/`, with post files `content/posts/2026-11-04-0*.md`. The 3 older queued posts are text. `bot/platforms/meta.py:87` and `bot/platforms/others.py:131` show that Instagram, TikTok and YouTube don't accept text posts, so these 3 reach none of them.
3. **The bot can't see results.** It has no code that reads views, shares or follows, so the test below has to be read by hand from each app's Insights.

## Decided by Ashikur (2026-11-04)

- **Audience:** US and UK.
- **Main need:** the line under "Fix the message", "mostly yes", so small changes are still possible.
- **On camera:** no. The account is faceless, so it needs a visual signature.

## Plan

### 1. Fix the message

One line: who it's for, and the one need every Reel serves.

> Small business owners whose website is losing them customers.

Check any grid against it: do the last 9 posts all clearly serve that need?

### 2. Set up the profile

These are one-time manual steps, which this project's rules allow.

- **Warm-up:** for 2 to 3 days on mobile, like and save only niche Reels, 3 to 4 times a day for 10 minutes. Note the best accounts.
- **Bio:** keywords in the name field; line 1 what it is; line 2 what the follower gets; line 3 a reason to stay. Keep it short.
- **Map the niche:** log topics, formats and hooks from big, medium and small creators. Note what you disagree with. Those notes are the raw material for Reels.

### 3. Run the test: 9 Reels

Three formats, three Reels each, made with `E:\Editing\docs\REELS.md`:

| Format | Example |
|---|---|
| Insider list | "Three things I'd never put on a client's homepage as a web designer" |
| Negative hook | "You're losing customers if your site still does this" |
| Non-negotiables | "If your site loads in under 2 seconds, you..." with a screen for each point |

Change nothing else between Reels. Then compare the top 3 on hook, format, caption, on-screen title and visuals.

**Judge by** views first (Steven Wommack), then shares (Tube Sensei), then profile visits, follows and enquiries (heyDominik). If views are high and enquiries are zero, per heyDominik the offer or audience is the problem, not the hooks.

### 4. Keep going to 20

Post the winning pattern until the profile has about 20 Reels on the one need. Per heyDominik, that's what a new viewer needs to see within about 30 days.

The video's arithmetic doesn't quite hold: 3 to 4 Reels a week gives 13 to 17 in 30 days, and 20 needs about 5 a week. The bot has 14 slots a week, so the limit is how fast the studio can make video. Video generation there is still untimed.

## Post file format

```yaml
---
media: [reel-name.mp4]
title: Short title
hashtags: [webdesign, smallbusiness, websitetips]
---
Hook line, usually a question.

The substance: advice, story or steps. Keywords belong here.

Follow for more on websites that bring in customers.
```

Use 3 to 7 hashtags, mixing one-word and multi-word (Grow with Alex). `config.yaml` caps Instagram at 5, which fits. Don't sell in the caption or bio until there's traction, per the same source. Note that this conflicts with the default goal: when to start asking for enquiries is Ashikur's call.

## Posting times

Slots in `config.yaml`, in winter time (Dhaka is UTC+6, New York UTC-5, London UTC+0). In summer, both move one hour later on the clock.

| Slot (Dhaka) | London | New York |
|---|---|---|
| 19:00 | 13:00, lunch | 08:00, morning rush |
| 23:00 | 17:00, two hours before the evening peak | 12:00, lunch |

These fit Grow with Alex's three peaks, and both markets get a useful time from the same slot. They're a starting point: check Insights once Reels are live.

- **US evening peak:** Grow with Alex's example, 4 to 5 pm EST, is 03:00 to 04:00 in Dhaka. To target it, set `publish_at` on that post.
- Per Grow with Alex, content and language decide the audience more than timing does.

## Tactics the bot can't do

The bot has no code for these, and this project doesn't allow recurring manual work, so they're skipped unless Ashikur chooses to post by hand. Whether Meta's API allows any of them wasn't checked.

- Trending audio, Instagram effects, polls in captions
- Pinned comments and pinned Reels

## Rejected

- **Downloading other people's Reels and reposting their clips, or Pinterest clips.** Rights risk (**inferred**). Copy structure only.
- **Copying outliers with no point of view.** heyDominik says it gets a profile written off. Grow with Alex, Steven Wommack and Tube Sensei recommend it. For a studio selling its own judgment, this plan leans on opinion (**inferred**). Run it as a test if Ashikur wants to.
- **Running AI captions through a humaniser** to avoid detection (Grow with Alex).
- **Aged Gmail for new accounts.** The accounts already exist.

## Check before relying on

**Evergreen reposts.** All 3 queued posts are `evergreen: true`, and the bot reposts one after 24 idle hours. That could fill the first 9 posts with repeats, which is what a new viewer judges the account by (**inferred**). Consider turning evergreen off on Reels that don't serve the main need.

## Open decisions for Ashikur

1. Facebook: `default_platforms` posts everywhere. Grow with Alex says Facebook views don't help Instagram; Tube Sensei says keep the reach. The bot posts to Facebook separately, so this is only a question of whether Facebook matters. (C-18)
