# Handoff: moving to a new PC (2026-11-03)

## What this project is

Social Autopilot posts your content to your social media accounts by itself, on a schedule,
even when you are offline for weeks. It costs nothing: it uses only free tools and free APIs.

- **Code and posts:** https://github.com/777-xevill/social-media (public repo)
- **Runs on:** GitHub Actions, every 15 minutes. Your PC can be off.
- **Media and legal pages:** GitHub Pages at https://777-xevill.github.io/social-media/
- **Alerts:** GitHub issues, which GitHub emails to you
- **Schedule:** queue slots at 10:00 and 19:00 (Asia/Dhaka). When the queue is empty,
  evergreen posts are re-posted.

| Platform | How it posts | Notes |
|---|---|---|
| Facebook, Instagram | Meta Graph API | Page token never expires |
| Threads | Threads API | Bot refreshes the token itself |
| YouTube | YouTube Data API | Uploads stay private until Google's free audit passes |
| LinkedIn | Posts API | Reconnect every ~60 days (the bot emails you) |
| Pinterest | API v5 | Sandbox until Standard access is approved |
| X, TikTok | Buffer free plan | X's own API is paid, so posting goes through Buffer |
| Reddit | Reddit API | Off by default; needs Reddit's approval |
| Snapchat | No API | Reminder issues only; off by default |

## Where things stand

| Item | Status |
|---|---|
| Code, workflows, setup guide | ✅ Pushed (`main` = `f3ec373`) |
| GitHub Pages | ✅ Live |
| Platform accounts created | ✅ Done (you) |
| Accounts connected to the bot | ❌ Not yet: no `.env` and no GitHub Secrets exist |
| GitHub Actions runs | ❌ **Blocked:** every run since Nov 1 ends as `action_required` with 0 jobs |
| Real content | ❌ Only the 3 `_example-*` posts are in `content/posts/` |

## Step 1: Set up the new PC (10 min)

You need Git, Python 3.11+ and GitHub CLI (`winget install GitHub.cli`).

```powershell
git clone https://github.com/777-xevill/social-media.git C:\social-media
cd C:\social-media
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pytest
gh auth login -s workflow      # GitHub.com → HTTPS → log in with a browser
python -m pytest -q            # should print "23 passed"
python -m bot validate
```

The old PC had nothing you need to copy. There was no `.env`, and nothing else exists only
on that PC.

## Step 2: Unblock GitHub Actions (do this first)

Until this is fixed, nothing posts, even after you connect accounts.

1. Open https://github.com/777-xevill/social-media/actions and click the newest **Publish** run.
   If there's an **Approve and run** button, click it.
2. If there is no button, check your account:
   - github.com → Settings → **Emails**: your email must be **verified**.
   - github.com → Settings → **Billing**: there must be no warning or lock.

   New accounts are often held until this is done.
3. Then test it:
   ```powershell
   gh workflow run publish.yml -f dry_run=true
   gh run list --limit 3      # want "completed success", not "action_required"
   ```
4. If runs are still `action_required` after that, contact GitHub Support
   (https://support.github.com). Say: *"Workflow runs on my own public repo
   777-xevill/social-media are all stuck in action_required with no jobs."*

## Step 3: Connect the accounts (1–2 hours, once)

Follow **[SETUP.md](SETUP.md)**. It has every click for each platform. Every platform follows
the same pattern:

```powershell
python -m bot auth <platform>   # saves keys to your local .env
python -m bot secrets           # copies .env into GitHub Secrets
```

Recommended order:
1. **YouTube** (SETUP §5): start here, because Google's audit takes days to weeks.
2. **Pinterest** (§7): apply for Standard access early, for the same reason.
3. **Facebook + Instagram** (§2): `auth meta`. Remember to switch the Meta app to **Live**.
4. **Threads** (§3)
5. **Buffer → X + TikTok** (§4)
6. **LinkedIn** (§6)
7. Reddit and Snapchat are optional (§8, §9).

Then check everything:

```powershell
python -m bot health
```

⚠️ **Back up `.env`** to a private place, such as a password manager or private cloud storage.
**Never commit it.** It holds `TOKEN_STORE_KEY`. If you lose that key and run `auth` again on
another PC, the bot gets a new key and can't read `state/tokens.enc`. Threads and Pinterest
would then need to be reconnected.

## Step 4: Add real posts

```powershell
python -m bot new "My first post"    # creates content/posts/<date>-my-first-post.md
# put images or videos in content/media/, edit the post file, then:
python -m bot validate
python -m bot plan
git add content; git commit -m "Add posts"; git push
```

Mark a few posts `evergreen: true` so the bot always has something to post. Delete the
`_example-*` files once you have your own.

## Day-to-day

- **You:** add posts and push them. That's all.
- **Bot:** posts on schedule. It retries failures up to 3 times and opens an issue when it needs you.
- **Every ~60 days:** LinkedIn emails you to reconnect. Run `python -m bot auth linkedin`, then `python -m bot secrets`.
- **Every Monday:** the health check runs and warns you when fewer than 5 posts are queued.

## Using Claude Code on the new PC

Claude's memory from the old PC does not move to the new one. [CLAUDE.md](CLAUDE.md) in this
repo has the goals and rules, so a new Claude Code session picks them up automatically.
Open the folder and say something like *"read HANDOFF.md and help me with step 2"*.
