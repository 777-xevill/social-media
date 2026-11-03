# Social Autopilot: notes for Claude

The owner's personal social media manager. It must keep posting unattended for long periods
with no manual steps. Current status and next steps are in [HANDOFF.md](HANDOFF.md).
What to post and how to judge it is in [docs/GROWTH.md](docs/GROWTH.md). Read it before writing or scheduling content.

## Hard rules
- **Zero budget.** Use only free tools, plans and APIs. Never suggest paid subscriptions or paid APIs.
  X and TikTok go through Buffer's free plan for this reason.
- Keep hosting on free GitHub infrastructure. Actions cron and Pages need the repo to stay public.
- Manual steps are allowed only for one-time setup. Anything recurring must be automated or
  raised as a GitHub issue (GitHub emails the owner).
- Never commit `.env` or any token. Secrets live in GitHub Secrets (`python -m bot secrets`).
  Tokens the bot renews itself go in `state/tokens.enc`, encrypted with `TOKEN_STORE_KEY`.

## Layout
- `bot/` is the Python package (`python -m bot -h`). Platform code is in `bot/platforms/`.
- `config.yaml` holds the schedule (Asia/Dhaka, slots 10:00 and 19:00), the platforms and the evergreen settings.
- Posts go in `content/posts/`, media in `content/media/`, and `state/state.json` is committed by the workflow.
- `.github/workflows/`:
  - `publish.yml`: runs every 15 minutes.
  - `health.yml`: weekly.
  - `validate.yml`: runs on push.
- `site/` holds the privacy, terms and OAuth callback pages served by GitHub Pages.
- Tests: `python -m pytest -q`

## GitHub
- Account `777-xevill`, repo `777-xevill/social-media`, branch `main`.
- Pushing `.github/workflows/*` needs the gh `workflow` scope (`gh auth login -s workflow`).
