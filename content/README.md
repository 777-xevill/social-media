# Writing posts

1. Put photos and videos in `content/media/`.
2. Create one file per post in `content/posts/`, either by copying an `_example-…` file
   (without the `_`) or by running `python -m bot new "My post title"`.
3. Push to GitHub (or upload the files on github.com). That's it.

The bot checks the files within a minute (see the **Actions** tab) and posts them on schedule.

## When does a post go out?

- **With `publish_at: 2026-11-05 19:00`**: at that time, in the timezone set in `config.yaml`.
- **Without `publish_at`**: it joins the queue and takes the next free slot from
  `config.yaml` → `schedule`. Posts are queued in filename order, so date-prefixed names
  like `2026-11-03-launch.md` keep things tidy.
- **Evergreen**: if nothing new has gone out for a day (`evergreen.idle_hours`), the bot
  re-posts an older `evergreen: true` post. The same post isn't re-posted for 45 days.

Run `python -m bot plan` to see the upcoming schedule.

## Every setting

| Setting | What it does |
|---|---|
| *(text below the `---`)* | The caption. In a `.yaml` file, use `text:` instead. |
| `media` | Files in `content/media/`, e.g. `[clip.mp4]` or `[a.jpg, b.jpg]`. |
| `title` | Used for the YouTube title, Pinterest title, Reddit title and TikTok title. If missing, the first line of the text is used. |
| `hashtags` | `[a, b, c]`. Added per platform up to `max_hashtags` in config.yaml (Instagram 5, Threads 1, X 2, …). |
| `link` | Added to the caption where links work. Used as the click-through link on Pinterest and as a link card on LinkedIn and Facebook. |
| `publish_at` | Exact time. Leave it out to use the queue. |
| `platforms` | Only these platforms, e.g. `[instagram, tiktok]`. Default: `default_platforms` in config.yaml. |
| `evergreen` | `true` = may be re-posted later when the queue is empty. |
| `video_format` | `short` (default: Reels, Shorts, TikTok) or `long` (regular YouTube/Facebook video). |
| `alt` | Image description for accessibility (Pinterest, LinkedIn, X). |
| `x:`, `linkedin:`, `instagram:` … | A different caption for that platform. Either plain text, or settings: `text`, `title`, `link`, `hashtags`, `board_id` (Pinterest), `subreddit` (Reddit). |

## What goes where

| Post type | Goes to |
|---|---|
| Text only | Facebook, Threads, LinkedIn, X, Reddit |
| 1 image | Facebook, Instagram, Threads, LinkedIn, X, Pinterest, Snapchat reminder |
| Several images | Facebook, Instagram (carousel), Threads, LinkedIn, X (max 4), Pinterest (first image) |
| 1 video | Everything: Reels, Shorts, TikTok, Threads, LinkedIn, X, Pinterest video pin |

If a post doesn't fit a platform (e.g. a text post and YouTube), that platform is skipped
for that post. Nothing breaks.

## Media tips

- **Short videos:** vertical 9:16, MP4 (H.264), 3–90 seconds. One file then works on every platform.
- **Instagram images must be `.jpg`.** PNG works everywhere else.
- **Size:** GitHub refuses files over 100 MB. Keep videos under ~95 MB.
- **Long captions:** if the text is too long for a platform (X allows 280 characters, Threads
  500), it's shortened automatically. The check on GitHub warns you so you can add an `x:` version.
