# Setup guide

Do these once. Connect platforms in any order, and come back for the rest later. Until a
platform is connected the bot skips it. Each connection ends with:

```powershell
python -m bot secrets      # copies your local .env to GitHub Secrets
```

> **Your callback page** (several apps ask for it): `https://777-xevill.github.io/social-media/site/oauth.html`
> **Privacy policy URL:** `https://777-xevill.github.io/social-media/site/privacy.html`
> **Terms URL:** `https://777-xevill.github.io/social-media/site/terms.html`
> **Website:** `https://777-xevill.github.io/social-media/`
> (If your repo has another name, change `site_url` in `config.yaml` and use that address.)

---

## 0. Your computer (5 min, once)

```powershell
cd C:\social-media
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
gh auth login        # already done on this PC
```

## 1. GitHub repo + Pages (5 min)

1. Create a **public** repo named `social-media` and push this folder to it.
2. Repo → **Settings → Pages** → Source: *Deploy from a branch* → `main` / `/ (root)` → Save.
3. After about a minute, open the privacy policy URL above. It should load.
4. Repo → **Settings → Actions → General** → Workflow permissions: *Read and write* → Save.
5. Make sure GitHub emails you: github.com → **Settings → Notifications** → *Watching* → Email ✓.

## 2. Facebook Page + Instagram (20 min)

You need a Facebook **Page** and an Instagram **Professional** (Business or Creator) account
linked to it. To link them: Instagram app → Settings → Account type and tools → switch to Professional,
then Facebook Page → Settings → Linked accounts → Instagram.

1. Go to <https://developers.facebook.com/apps> → **Create app**.
   - Use cases: **Manage everything on your Page**, and **Manage messaging & content on Instagram**
     (choose *API setup with Facebook login*).
   - App type, if asked: *Business*.
2. App settings → Basic: fill in **Privacy Policy URL** and **Terms of Service URL**
   (above). For **User data deletion**, use the privacy policy URL. Add an app icon and a category. Save.
3. Copy the **App ID** and **App Secret** from the same page.
4. Run:
   ```powershell
   python -m bot auth meta
   ```
   It asks for the App ID and Secret, then for a token from the Graph API Explorer (the command
   explains exactly which boxes to tick). It saves a Page token that **never expires**.
5. Back in the app dashboard, switch **App Mode** from *Development* to **Live**.
   Without this, API posts are visible only to you.
6. `python -m bot secrets`

## 3. Threads (10 min)

1. <https://developers.facebook.com/apps> → **Create app** → use case **Access the Threads API**.
   Keep it separate from the Facebook app.
2. Use cases → Threads API → **Settings**:
   - Redirect callback URL, Uninstall callback URL and Delete callback URL: all set to your callback page.
   - Copy the **Threads App ID** and **Threads App Secret**.
3. App roles → Roles → **Add Threads Tester** → your Threads username. Then in the Threads app:
   Settings → Account → Website permissions → Invites → **Accept**.
4. Same as step 2.2 for the Facebook app: privacy policy URL, icon, category.
5. `python -m bot auth threads` → approve in the browser → paste the code shown → `python -m bot secrets`

The bot renews this token weekly by itself.

## 4. Buffer: X and TikTok (10 min)

X's own API costs money per post (since Feb 2026), and TikTok only lets personal apps post
privately. Buffer's **free** plan posts to both, and its API is free too.

1. Sign up at <https://buffer.com> (Free plan) and connect **X** and **TikTok** as channels.
2. Create an API key: <https://publish.buffer.com/settings/api> (or Settings → API).
3. `python -m bot auth buffer` → it finds your channels → `python -m bot secrets`

The free plan has 3 channels. Use the third for YouTube or Pinterest while their approvals
are pending: connect it in Buffer, set `via: buffer` for it in `config.yaml`, then re-run
`python -m bot auth buffer`.

## 5. YouTube (20 min + waiting for the audit)

1. <https://console.cloud.google.com> → create a project named, for example, *social-autopilot*.
2. **APIs & Services → Library** → *YouTube Data API v3* → **Enable**.
3. **Google Auth Platform** (OAuth consent screen):
   - Branding: app name, your email, home page = website, privacy policy URL.
   - Audience: *External*, then click **Publish app** so the status is **In production**.
     *In "Testing" mode Google kills the login after 7 days.*
4. **Clients → Create client** → type **Desktop app** → copy Client ID and Secret.
5. `python -m bot auth youtube` → sign in. You'll see "Google hasn't verified this app": click
   **Advanced → Go to … (unsafe)**. It's your own app, so this is expected. Then `python -m bot secrets`.
6. **The audit (important):** Google forces videos uploaded by un-audited API projects to *private*.
   Fill in the free [YouTube API Services audit form](https://support.google.com/youtube/contact/yt_api_form)
   for this project. Use case: "personal tool that uploads my own videos to my own channel".
   Until it's approved, either accept private uploads or set `youtube: via: buffer` (Buffer's spare channel).

## 6. LinkedIn (15 min, then 2 min every ~60 days)

1. <https://www.linkedin.com/developers/apps> → **Create app**. LinkedIn requires a company Page to
   associate. Create a free one if you don't have one. It only labels the app.
2. **Auth** tab → Authorized redirect URLs → add your callback page. Copy Client ID and Secret.
3. **Products** tab → request **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**.
   Both are approved instantly.
4. `python -m bot auth linkedin` → approve → paste code → `python -m bot secrets`

LinkedIn tokens last 60 days and LinkedIn doesn't let personal apps renew them. The weekly
health check emails you 2 weeks before expiry. Then re-run the two commands above.

## 7. Pinterest (15 min + approval)

1. Convert to (or create) a free **Pinterest Business** account and create at least one board.
2. <https://developers.pinterest.com/apps/> → **Connect app**: website, privacy policy URL,
   and redirect URI = your callback page. Copy the App ID and App secret key.
3. Your app starts with **Trial access**: pins are created in a sandbox and hidden from the public.
   Set `pinterest: sandbox: true` in `config.yaml` for now.
4. `python -m bot auth pinterest` → pick a board → `python -m bot secrets`
5. Apply for **Standard access** in the app's page. Pinterest wants a short screen recording showing
   the login (step 4) and a pin being created (run `python -m bot run` with a test post). After
   approval, set `sandbox: false`.

Alternative while waiting: Pinterest through Buffer's spare channel (`via: buffer`).

## 8. Reddit (optional, needs approval)

Since November 2025 Reddit reviews every API request by hand and often declines small personal
tools. Also, most subreddits ban automated self-promotion, and accounts get banned for it.
If you still want it:

1. Request API access through Reddit's developer support form (linked from
   <https://www.reddit.com/prefs/apps>). Describe it as a personal tool posting to your own profile.
2. Once approved: <https://www.reddit.com/prefs/apps> → create app → type **script**.
3. `python -m bot auth reddit`, then in `config.yaml`: `reddit: enabled: true, subreddit: u_YOURNAME`.
4. `python -m bot secrets`

## 9. Snapchat (optional)

Snapchat has no self-serve posting API. If you set `snapchat: enabled: true`, every image or
video post opens a GitHub issue (an email) with the file links and caption. Posting it by hand
takes about 30 seconds.

## 10. Check everything

GitHub → **Actions → Health check → Run workflow**. The run summary shows a table with ✅ / ❌
for each platform. Then add a post and watch **Actions → Publish**.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "isn't live on GitHub Pages yet" | Normal for 1–2 min after a push. The bot retries next run. If it persists, check step 1.2. |
| Instagram skips a post | Images must be `.jpg`. Max 10 items. |
| YouTube videos are private | The audit isn't approved yet (step 5.6). |
| Posts only visible to you on Facebook | The Meta app is still in Development mode (step 2.5). |
| `invalid_grant` from YouTube | The OAuth app was in Testing mode. Publish it (5.3) and re-run `auth youtube`. |
| Got an email "posts failed" | Open the issue. It names the platform, the error and the fix. Close it when handled. |
| Repost something | Delete the post's entry in `state/state.json`, or copy the post file under a new name. |
| Pause everything | Actions → Publish → ••• → **Disable workflow**. |
