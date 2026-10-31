"""One-time account connection helpers. Run locally: `python -m bot auth <platform>`.

Each helper saves what it gets into .env; `python -m bot secrets` then copies .env to
GitHub Secrets. OAuth providers that need an https redirect send you to this repo's
GitHub Pages page (site/oauth.html), which shows the code to paste back here.
"""
from __future__ import annotations

import getpass
import shutil
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key

from .config import ENV_FILE, ROOT, Config
from .net import ApiError, request

GRAPH = "https://graph.facebook.com"


def _env() -> dict:
    return dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}


def save(key: str, value: str) -> None:
    ENV_FILE.touch(exist_ok=True)
    set_key(str(ENV_FILE), key, value, quote_mode="never")


def ask(key: str, prompt: str, secret: bool = False) -> str:
    current = _env().get(key)
    if current:
        return current
    value = (getpass.getpass if secret else input)(f"{prompt}: ").strip()
    if not value:
        raise SystemExit(f"{key} is required")
    save(key, value)
    return value


def choose(items: list[dict], label) -> dict:
    if len(items) == 1:
        return items[0]
    for i, item in enumerate(items, 1):
        print(f"  {i}. {label(item)}")
    return items[int(input("Pick a number: ").strip()) - 1]


def ensure_store_key() -> None:
    if not _env().get("TOKEN_STORE_KEY"):
        save("TOKEN_STORE_KEY", Fernet.generate_key().decode())


def callback_url(cfg: Config) -> str:
    return f"{cfg.site_url}/site/oauth.html"


def browser_code(url: str) -> str:
    print(f"\nOpening your browser. If it doesn't open, visit:\n{url}\n")
    webbrowser.open(url)
    raw = input("Paste the code shown on the page (or the whole address bar URL): ").strip()
    if raw.startswith("http"):
        raw = (parse_qs(urlparse(raw).query).get("code") or [""])[0]
    return raw.removesuffix("#_").strip()


def meta(cfg: Config) -> None:
    v = cfg.graph_version
    app_id = ask("META_APP_ID", "Meta App ID")
    app_secret = ask("META_APP_SECRET", "Meta App Secret", secret=True)
    print(f"""
1. Open https://developers.facebook.com/tools/explorer/
2. 'Meta App' → pick your app.  'User or Page' → User Token.
3. Add permissions: pages_show_list, pages_read_engagement, pages_manage_posts,
   business_management, instagram_basic, instagram_content_publish
4. Click 'Generate Access Token', approve, and copy the token.""")
    short = getpass.getpass("Paste the token (hidden): ").strip()
    long_user = request("GET", f"{GRAPH}/{v}/oauth/access_token", "meta", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": short}).json()["access_token"]
    pages = request("GET", f"{GRAPH}/{v}/me/accounts", "meta", params={
        "fields": "id,name,access_token,instagram_business_account{id,username}",
        "access_token": long_user}).json().get("data", [])
    if not pages:
        raise SystemExit("No Facebook Pages found — make sure you selected your Page when approving.")
    page = choose(pages, lambda p: p["name"])
    save("FACEBOOK_PAGE_ID", page["id"])
    save("FACEBOOK_PAGE_TOKEN", page["access_token"])
    info = request("GET", f"{GRAPH}/{v}/debug_token", "meta", params={
        "input_token": page["access_token"], "access_token": f"{app_id}|{app_secret}"}).json()["data"]
    print(f"✓ Facebook Page: {page['name']} (token expires: "
          f"{'never' if not info.get('expires_at') else info['expires_at']})")
    ig = page.get("instagram_business_account")
    if ig:
        save("INSTAGRAM_USER_ID", ig["id"])
        print(f"✓ Instagram: @{ig.get('username')}")
    else:
        print("⚠ No Instagram professional account is linked to this Page (see SETUP.md › Instagram).")


def threads(cfg: Config) -> None:
    app_id = ask("THREADS_APP_ID", "Threads App ID (Meta app → Use cases → Threads API → Settings)")
    secret = ask("THREADS_APP_SECRET", "Threads App Secret", secret=True)
    redirect = callback_url(cfg)
    code = browser_code("https://threads.net/oauth/authorize?" + urlencode({
        "client_id": app_id, "redirect_uri": redirect, "response_type": "code",
        "scope": "threads_basic,threads_content_publish"}))
    short = request("POST", "https://graph.threads.net/oauth/access_token", "threads", data={
        "client_id": app_id, "client_secret": secret, "grant_type": "authorization_code",
        "redirect_uri": redirect, "code": code}).json()
    long = request("GET", "https://graph.threads.net/access_token", "threads", params={
        "grant_type": "th_exchange_token", "client_secret": secret,
        "access_token": short["access_token"]}).json()
    save("THREADS_USER_ID", str(short["user_id"]))
    save("THREADS_ACCESS_TOKEN", long["access_token"])
    print("✓ Threads connected (the bot refreshes this token automatically).")


def youtube(cfg: Config) -> None:
    cid = ask("YOUTUBE_CLIENT_ID", "Google OAuth Client ID (Desktop app)")
    secret = ask("YOUTUBE_CLIENT_SECRET", "Google OAuth Client Secret", secret=True)
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            result.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Done — you can close this tab and go back to the terminal.</h2>".encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "access_type": "offline",
        "prompt": "consent", "scope": "https://www.googleapis.com/auth/youtube.upload "
                                      "https://www.googleapis.com/auth/youtube.readonly"})
    print(f"\nOpening your browser to sign in with Google. If it doesn't open, visit:\n{url}\n")
    threading.Timer(0.5, webbrowser.open, [url]).start()
    while "code" not in result and "error" not in result:
        server.handle_request()
    if "error" in result:
        raise SystemExit(f"Google sign-in failed: {result['error']}")
    tokens = request("POST", "https://oauth2.googleapis.com/token", "youtube", data={
        "code": result["code"], "client_id": cid, "client_secret": secret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}).json()
    if "refresh_token" not in tokens:
        raise SystemExit("Google didn't return a refresh token — remove the app's access at "
                         "https://myaccount.google.com/permissions and try again.")
    save("YOUTUBE_REFRESH_TOKEN", tokens["refresh_token"])
    print("✓ YouTube connected.")


def linkedin(cfg: Config) -> None:
    cid = ask("LINKEDIN_CLIENT_ID", "LinkedIn Client ID")
    secret = ask("LINKEDIN_CLIENT_SECRET", "LinkedIn Client Secret", secret=True)
    redirect = callback_url(cfg)
    code = browser_code("https://www.linkedin.com/oauth/v2/authorization?" + urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": redirect,
        "scope": "openid profile w_member_social"}))
    tok = request("POST", "https://www.linkedin.com/oauth/v2/accessToken", "linkedin", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
        "client_id": cid, "client_secret": secret}).json()
    me = request("GET", "https://api.linkedin.com/v2/userinfo", "linkedin",
                 headers={"Authorization": f"Bearer {tok['access_token']}"}).json()
    save("LINKEDIN_ACCESS_TOKEN", tok["access_token"])
    save("LINKEDIN_PERSON_URN", f"urn:li:person:{me['sub']}")
    days = int(tok.get("expires_in", 0)) // 86400
    print(f"✓ LinkedIn: {me.get('name')}. Token lasts {days} days — the bot emails you 2 weeks before it ends.")


def pinterest(cfg: Config) -> None:
    app_id = ask("PINTEREST_APP_ID", "Pinterest App ID")
    secret = ask("PINTEREST_APP_SECRET", "Pinterest App secret key", secret=True)
    redirect = callback_url(cfg)
    code = browser_code("https://www.pinterest.com/oauth/?" + urlencode({
        "client_id": app_id, "redirect_uri": redirect, "response_type": "code",
        "scope": "boards:read,boards:write,pins:read,pins:write,user_accounts:read"}))
    tok = request("POST", "https://api.pinterest.com/v5/oauth/token", "pinterest", auth=(app_id, secret),
                  data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect}).json()
    save("PINTEREST_REFRESH_TOKEN", tok["refresh_token"])
    host = "api-sandbox.pinterest.com" if cfg.platform("pinterest").get("sandbox") else "api.pinterest.com"
    boards = request("GET", f"https://{host}/v5/boards", "pinterest",
                     headers={"Authorization": f"Bearer {tok['access_token']}"}).json().get("items", [])
    if boards:
        print("Which board should pins go to?")
        board = choose(boards, lambda b: b["name"])
        save("PINTEREST_BOARD_ID", board["id"])
        print(f"✓ Pinterest connected — pinning to '{board['name']}'.")
    else:
        print("✓ Pinterest connected. ⚠ No boards found: create one, then set board_id in config.yaml.")


def buffer(cfg: Config) -> None:
    key = ask("BUFFER_API_KEY", "Buffer API key (publish.buffer.com → Settings → API)", secret=True)
    gql = lambda q: request("POST", "https://api.buffer.com", "buffer", json={"query": q},
                            headers={"Authorization": f"Bearer {key}"}).json()["data"]
    services = {"twitter": "x", "tiktok": "tiktok", "youtube": "youtube", "pinterest": "pinterest",
                "linkedin": "linkedin", "threads": "threads", "instagram": "instagram", "facebook": "facebook"}
    for org in gql("query { account { organizations { id name } } }")["account"]["organizations"]:
        channels = gql(f'query {{ channels(input: {{ organizationId: "{org["id"]}" }}) {{ id name service }} }}')
        for ch in channels["channels"]:
            platform = services.get(ch["service"])
            if platform:
                save(f"BUFFER_CHANNEL_{platform.upper()}", ch["id"])
                print(f"✓ {platform}: {ch['name']} (Buffer channel {ch['id']})")
    print("Platforms set to `via: buffer` in config.yaml will post through these channels.")


def reddit(cfg: Config) -> None:
    cid = ask("REDDIT_CLIENT_ID", "Reddit app client ID (under the app name)")
    secret = ask("REDDIT_CLIENT_SECRET", "Reddit app secret", secret=True)
    user = ask("REDDIT_USERNAME", "Reddit username")
    pw = ask("REDDIT_PASSWORD", "Reddit password", secret=True)
    try:
        request("POST", "https://www.reddit.com/api/v1/access_token", "reddit", auth=(cid, secret),
                headers={"User-Agent": f"python:social-autopilot:1.0 (by /u/{user})"},
                data={"grant_type": "password", "username": user, "password": pw}).json()["access_token"]
    except (ApiError, KeyError) as e:
        raise SystemExit(f"Reddit login failed: {e}. Is your API access approved yet?")
    print(f"✓ Reddit: u/{user}")


FLOWS = {"meta": meta, "threads": threads, "youtube": youtube, "linkedin": linkedin,
         "pinterest": pinterest, "buffer": buffer, "reddit": reddit}


def run(platform: str) -> None:
    ensure_store_key()
    FLOWS[platform](Config())
    print("\nNext: `python -m bot secrets` to send these to GitHub.")


def push_secrets() -> None:
    if not ENV_FILE.exists():
        raise SystemExit("No .env yet — connect a platform first with `python -m bot auth <platform>`.")
    if not shutil.which("gh"):
        raise SystemExit("GitHub CLI (gh) not found — install it from https://cli.github.com/")
    ensure_store_key()
    subprocess.run(["gh", "secret", "set", "-f", str(ENV_FILE)], cwd=ROOT, check=True)
    print(f"✓ Sent {len(_env())} secrets to GitHub.")
