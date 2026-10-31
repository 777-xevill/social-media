"""Pinterest, Reddit, Buffer (bridge for X / TikTok / others) and the Snapchat reminder."""
from __future__ import annotations

import base64

from ..content import Rendered
from ..media import mime, public_url
from ..net import ApiError, request
from .base import Adapter


class Pinterest(Adapter):
    name = "pinterest"
    secrets_needed = ("PINTEREST_APP_ID", "PINTEREST_APP_SECRET", "PINTEREST_REFRESH_TOKEN")
    supports = {"image", "images", "video"}
    setup_hint = "run `python -m bot auth pinterest`"
    _token: str | None = None

    @property
    def base(self) -> str:
        host = "api-sandbox.pinterest.com" if self.pcfg.get("sandbox") else "api.pinterest.com"
        return f"https://{host}/v5"

    def token(self) -> str:
        if not self._token:
            seed = self.secret("PINTEREST_REFRESH_TOKEN")
            stored = self.ctx.tokens.get("pinterest") or {}
            refresh = stored["refresh_token"] if stored.get("seed") == seed else seed
            try:
                res = request("POST", "https://api.pinterest.com/v5/oauth/token", self.name,
                              auth=(self.secret("PINTEREST_APP_ID"), self.secret("PINTEREST_APP_SECRET")),
                              data={"grant_type": "refresh_token", "refresh_token": refresh}).json()
            except ApiError as e:
                raise ApiError(self.name, f"token refresh failed: {e}", e.status, auth=True) from e
            self._token = res["access_token"]
            if res.get("refresh_token"):
                self.ctx.tokens.set("pinterest", {"refresh_token": res["refresh_token"], "seed": seed})
        return self._token

    def _api(self, method: str, path: str, **kw):
        return request(method, f"{self.base}{path}", self.name,
                       headers={"Authorization": f"Bearer {self.token()}"}, **kw)

    def board(self, r: Rendered) -> str | None:
        return str(r.options.get("board_id") or self.secret("PINTEREST_BOARD_ID") or "") or None

    def incompatible(self, r: Rendered) -> str | None:
        reason = super().incompatible(r)
        if not reason and not self.board(r):
            reason = "no Pinterest board — set platforms.pinterest.board_id in config.yaml"
        return reason

    def publish(self, r: Rendered) -> dict:
        if r.post.kind == "video":
            source = self._upload_video(r.media_paths[0])
        else:
            path = r.media_paths[0]
            source = {"source_type": "image_base64", "content_type": mime(path),
                      "data": base64.b64encode(path.read_bytes()).decode()}
        body = {"board_id": self.board(r), "title": r.title[:100], "description": r.text[:800],
                "media_source": source}
        if r.link:
            body["link"] = r.link
        if r.post.alt:
            body["alt_text"] = r.post.alt[:500]
        pin = self._api("POST", "/pins", json=body).json()
        return {"id": pin["id"], "url": f"https://www.pinterest.com/pin/{pin['id']}/"}

    def _upload_video(self, path) -> dict:
        reg = self._api("POST", "/media", json={"media_type": "video"}).json()
        with open(path, "rb") as f:
            request("POST", reg["upload_url"], self.name, data=reg["upload_parameters"],
                    files={"file": f}, timeout=1200)

        def ready():
            status = self._api("GET", f"/media/{reg['media_id']}").json().get("status")
            if status == "failed":
                raise ApiError(self.name, "Pinterest couldn't process the video")
            return status == "succeeded"

        self.wait_until(ready, "Pinterest to process the video", timeout=900)
        return {"source_type": "video_id", "media_id": reg["media_id"], "cover_image_key_frame_time": 0}

    def health(self) -> str:
        return f"@{self._api('GET', '/user_account').json().get('username')}"


class Reddit(Adapter):
    name = "reddit"
    secrets_needed = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD")
    supports = {"text"}
    setup_hint = "see SETUP.md › Reddit"

    @property
    def ua(self) -> str:
        return f"python:social-autopilot:1.0 (by /u/{self.secret('REDDIT_USERNAME')})"

    def token(self) -> str:
        return request("POST", "https://www.reddit.com/api/v1/access_token", self.name,
                       auth=(self.secret("REDDIT_CLIENT_ID"), self.secret("REDDIT_CLIENT_SECRET")),
                       headers={"User-Agent": self.ua},
                       data={"grant_type": "password", "username": self.secret("REDDIT_USERNAME"),
                             "password": self.secret("REDDIT_PASSWORD")}).json()["access_token"]

    def incompatible(self, r: Rendered) -> str | None:
        if r.post.kind != "text" and "reddit" not in r.post.overrides:
            return "media posts only go to Reddit when the post has its own `reddit:` section"
        if not r.options.get("subreddit"):
            return "no subreddit — set platforms.reddit.subreddit in config.yaml"
        return None

    def publish(self, r: Rendered) -> dict:
        sr = str(r.options["subreddit"]).removeprefix("r/").removeprefix("/r/")
        data = {"sr": sr, "title": r.title[:300], "api_type": "json", "resubmit": "true"}
        data.update({"kind": "link", "url": r.link} if r.link else {"kind": "self", "text": r.text})
        res = request("POST", "https://oauth.reddit.com/api/submit", self.name, data=data,
                      headers={"Authorization": f"Bearer {self.token()}", "User-Agent": self.ua}).json()["json"]
        if res.get("errors"):
            raise ApiError(self.name, "; ".join(" ".join(map(str, e)) for e in res["errors"]))
        return {"id": res["data"].get("name"), "url": res["data"].get("url")}

    def health(self) -> str:
        res = request("GET", "https://oauth.reddit.com/api/v1/me", self.name,
                      headers={"Authorization": f"Bearer {self.token()}", "User-Agent": self.ua}).json()
        return f"u/{res.get('name')}"


BUFFER_SERVICE = {"x": "twitter", "tiktok": "tiktok", "youtube": "youtube", "pinterest": "pinterest",
                  "linkedin": "linkedin", "threads": "threads"}
BUFFER_SUPPORTS = {
    "x": {"text", "image", "images", "video"}, "tiktok": {"video"}, "youtube": {"video"},
    "pinterest": {"image", "video"}, "linkedin": {"text", "image", "images", "video"},
    "threads": {"text", "image", "images", "video"},
}
CREATE_POST = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}"""


class Buffer(Adapter):
    """Posts through Buffer's free API (3 channels). Buffer fetches media from GitHub Pages."""
    setup_hint = "run `python -m bot auth buffer`"

    def __init__(self, ctx, platform: str):
        self.name = platform
        super().__init__(ctx)
        self.secrets_needed = ("BUFFER_API_KEY", f"BUFFER_CHANNEL_{platform.upper()}")
        self.supports = BUFFER_SUPPORTS.get(platform, set())

    def incompatible(self, r: Rendered) -> str | None:
        if self.name not in BUFFER_SERVICE:
            return f"{self.name} via Buffer isn't supported — set `via: direct` in config.yaml"
        if self.name == "x" and len(r.post.images) > 4:
            return "X takes at most 4 images"
        return super().incompatible(r)

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        res = request("POST", "https://api.buffer.com", self.name, json={"query": query, "variables": variables or {}},
                      headers={"Authorization": f"Bearer {self.secret('BUFFER_API_KEY')}"}).json()
        if res.get("errors"):
            msg = "; ".join(e.get("message", "") for e in res["errors"])
            raise ApiError(self.name, f"Buffer: {msg}", auth="auth" in msg.lower())
        return res["data"]

    def publish(self, r: Rendered) -> dict:
        assets = []
        media = r.post.media[:1] if r.post.kind == "video" or self.name == "pinterest" else r.post.media
        for rel in media:
            url = public_url(self.ctx.cfg, rel)
            if rel in r.post.images:
                image = {"url": url}
                if r.post.alt:
                    image["metadata"] = {"altText": r.post.alt}
                assets.append({"image": image})
            else:
                assets.append({"video": {"url": url, "metadata": {"title": r.title[:100]}}})
        data = {"text": r.text, "channelId": self.secret(f"BUFFER_CHANNEL_{self.name.upper()}"),
                "schedulingType": "automatic", "mode": "shareNow", "assets": assets}
        meta = {
            "tiktok": {"tiktok": {"title": r.title[:90]}},
            "youtube": {"youtube": {"title": r.title[:100],
                                    "categoryId": str(self.pcfg.get("category_id", "22"))}},
            "pinterest": {"pinterest": {k: v for k, v in {
                "boardServiceId": str(r.options.get("board_id") or self.secret("PINTEREST_BOARD_ID") or ""),
                "title": r.title[:100],
                "url": r.link}.items() if v}},
        }.get(self.name)
        if meta:
            data["metadata"] = meta
        result = self.graphql(CREATE_POST, {"input": data})["createPost"]
        if "post" not in result:
            raise ApiError(self.name, f"Buffer: {result.get('message', 'unknown error')}")
        return {"id": result["post"]["id"], "url": "https://publish.buffer.com/"}

    def health(self) -> str:
        orgs = self.graphql("query { account { organizations { id name } } }")["account"]["organizations"]
        return f"Buffer org: {', '.join(o['name'] for o in orgs)}"


class Snapchat(Adapter):
    """No public posting API — opens a GitHub issue (= email) with the caption and media links."""
    name = "snapchat"
    supports = {"image", "video"}
    setup_hint = "runs inside GitHub Actions only"

    def missing_secrets(self) -> list[str]:
        return [] if self.ctx.github.enabled else ["GITHUB_TOKEN"]

    def publish(self, r: Rendered) -> dict:
        links = "\n".join(f"- {self.ctx.cfg.media_url(m)}" for m in r.post.media)
        body = (f"Snapchat has no public posting API, so this one needs you (about 30 seconds):\n\n"
                f"1. Download the media:\n{links}\n2. Post it to Spotlight/Story with this caption:\n\n"
                f"```\n{r.text}\n```\n\nClose this issue when done.")
        url = self.ctx.github.alert(f"📲 Post to Snapchat: {r.title[:60]}", body, label="manual-post")
        if not url:
            raise ApiError(self.name, "couldn't create the reminder issue")
        return {"id": "reminder", "url": url}


class Unsupported(Adapter):
    REASONS = {
        "x": "X's own API is paid-only since Feb 2026 — set `via: buffer` for x in config.yaml",
        "tiktok": "TikTok's API only allows private posts for personal apps — set `via: buffer`",
    }

    def __init__(self, ctx, platform: str):
        self.name = platform
        super().__init__(ctx)

    def incompatible(self, r: Rendered) -> str | None:
        return self.REASONS.get(self.name, f"{self.name} has no direct integration — try `via: buffer`")
