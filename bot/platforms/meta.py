"""Facebook Page, Instagram (professional account linked to the Page) and Threads."""
from __future__ import annotations

import json
from datetime import timedelta

from ..content import Rendered
from ..media import public_url
from ..net import ApiError, log, request
from ..state import iso, parse_iso, utcnow
from .base import Adapter


class Facebook(Adapter):
    name = "facebook"
    secrets_needed = ("FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_TOKEN")
    supports = {"text", "image", "images", "video"}
    setup_hint = "run `python -m bot auth meta`"

    @property
    def base(self) -> str:
        return f"https://graph.facebook.com/{self.ctx.cfg.graph_version}"

    def _post(self, path: str, data: dict | None = None, files=None, base: str | None = None) -> dict:
        data = {**(data or {}), "access_token": self.secret("FACEBOOK_PAGE_TOKEN")}
        return request("POST", f"{base or self.base}/{path}", self.name, data=data, files=files).json()

    def publish(self, r: Rendered) -> dict:
        page = self.secret("FACEBOOK_PAGE_ID")
        kind = r.post.kind
        if kind == "text":
            data = {"message": r.text}
            if r.link:
                data["link"] = r.link
            res = self._post(f"{page}/feed", data)
            return {"id": res["id"], "url": f"https://www.facebook.com/{res['id']}"}
        if kind == "image":
            path = r.media_paths[0]
            with open(path, "rb") as f:
                res = self._post(f"{page}/photos", {"caption": r.text}, files={"source": f})
            pid = res.get("post_id") or res["id"]
            return {"id": pid, "url": f"https://www.facebook.com/{pid}"}
        if kind == "images":
            ids = []
            for path in r.media_paths[:10]:
                with open(path, "rb") as f:
                    ids.append(self._post(f"{page}/photos", {"published": "false"}, files={"source": f})["id"])
            data = {"message": r.text}
            data.update({f"attached_media[{i}]": json.dumps({"media_fbid": mid}) for i, mid in enumerate(ids)})
            res = self._post(f"{page}/feed", data)
            return {"id": res["id"], "url": f"https://www.facebook.com/{res['id']}"}
        # video
        if r.is_short:
            try:
                return self._reel(page, r)
            except ApiError as e:
                log(f"facebook reel upload failed ({e}); posting as a regular video", "warning")
        path = r.media_paths[0]
        with open(path, "rb") as f:
            res = self._post(f"{page}/videos", {"description": r.text, "title": r.title[:250]},
                             files={"source": f}, base=self.base.replace("graph.", "graph-video."))
        return {"id": res["id"], "url": f"https://www.facebook.com/{page}/videos/{res['id']}"}

    def _reel(self, page: str, r: Rendered) -> dict:
        start = self._post(f"{page}/video_reels", {"upload_phase": "start"})
        vid = start["video_id"]
        path = r.media_paths[0]
        with open(path, "rb") as f:
            data = f.read()
        request("POST", f"https://rupload.facebook.com/video-upload/{self.ctx.cfg.graph_version}/{vid}",
                self.name, data=data, timeout=600, headers={
                    "Authorization": f"OAuth {self.secret('FACEBOOK_PAGE_TOKEN')}",
                    "offset": "0", "file_size": str(len(data))})
        self._post(f"{page}/video_reels", {"upload_phase": "finish", "video_id": vid,
                                           "video_state": "PUBLISHED", "description": r.text})
        return {"id": vid, "url": f"https://www.facebook.com/reel/{vid}"}

    def health(self) -> str:
        res = request("GET", f"{self.base}/{self.secret('FACEBOOK_PAGE_ID')}", self.name,
                      params={"fields": "name", "access_token": self.secret("FACEBOOK_PAGE_TOKEN")}).json()
        return f"Page: {res.get('name')}"


class Instagram(Facebook):
    name = "instagram"
    secrets_needed = ("INSTAGRAM_USER_ID", "FACEBOOK_PAGE_TOKEN")
    supports = {"image", "images", "video", "mixed"}

    def incompatible(self, r: Rendered) -> str | None:
        reason = super().incompatible(r)
        if reason:
            return reason
        if any(not p.lower().endswith((".jpg", ".jpeg")) for p in r.post.images):
            return "Instagram only accepts JPEG images (.jpg)"
        if len(r.post.media) > 10:
            return "Instagram carousels hold at most 10 items"
        return None

    def _container(self, params: dict) -> str:
        ig = self.secret("INSTAGRAM_USER_ID")
        cid = self._post(f"{ig}/media", params)["id"]

        def ready():
            res = request("GET", f"{self.base}/{cid}", self.name, params={
                "fields": "status_code,status", "access_token": self.secret("FACEBOOK_PAGE_TOKEN")}).json()
            if res.get("status_code") == "ERROR":
                raise ApiError(self.name, f"Instagram couldn't process the media: {res.get('status')}")
            return res.get("status_code") in ("FINISHED", "PUBLISHED")

        self.wait_until(ready, "Instagram to process the media", timeout=900)
        return cid

    def _item(self, rel: str, carousel: bool) -> dict:
        url = public_url(self.ctx.cfg, rel)
        if rel.lower().endswith((".jpg", ".jpeg")):
            params = {"image_url": url}
        else:
            params = {"video_url": url, "media_type": "VIDEO" if carousel else "REELS"}
        if carousel:
            params["is_carousel_item"] = "true"
        return params

    def publish(self, r: Rendered) -> dict:
        ig = self.secret("INSTAGRAM_USER_ID")
        media = r.post.media
        if len(media) == 1:
            params = {**self._item(media[0], carousel=False), "caption": r.text}
            if params.get("media_type") == "REELS":
                # false = the Reel lives in the Reels tab only, not on the main profile grid
                params["share_to_feed"] = "true" if self.pcfg.get("reels_on_grid", True) else "false"
            cid = self._container(params)
        else:
            children = [self._container(self._item(m, carousel=True)) for m in media]
            cid = self._container({"media_type": "CAROUSEL", "children": ",".join(children), "caption": r.text})
        mid = self._post(f"{ig}/media_publish", {"creation_id": cid})["id"]
        url = request("GET", f"{self.base}/{mid}", self.name, params={
            "fields": "permalink", "access_token": self.secret("FACEBOOK_PAGE_TOKEN")}).json().get("permalink")
        return {"id": mid, "url": url}

    def health(self) -> str:
        res = request("GET", f"{self.base}/{self.secret('INSTAGRAM_USER_ID')}", self.name, params={
            "fields": "username", "access_token": self.secret("FACEBOOK_PAGE_TOKEN")}).json()
        return f"@{res.get('username')}"


class Threads(Adapter):
    name = "threads"
    secrets_needed = ("THREADS_USER_ID", "THREADS_ACCESS_TOKEN")
    setup_hint = "run `python -m bot auth threads`"
    base = "https://graph.threads.net/v1.0"
    REFRESH_EVERY = timedelta(days=7)

    def token(self) -> str:
        """Long-lived tokens last 60 days; refresh weekly and keep the newest in the token store."""
        stored = self.ctx.tokens.get("threads") or {}
        token = stored.get("token") or self.secret("THREADS_ACCESS_TOKEN")
        if stored.get("seed") != self.secret("THREADS_ACCESS_TOKEN"):
            token, stored = self.secret("THREADS_ACCESS_TOKEN"), {}  # a fresh token was pushed
        refreshed = parse_iso(stored.get("refreshed_at"))
        if self.ctx.tokens.enabled and (refreshed is None or utcnow() - refreshed > self.REFRESH_EVERY):
            try:
                res = request("GET", "https://graph.threads.net/refresh_access_token", self.name,
                              params={"grant_type": "th_refresh_token", "access_token": token}).json()
                token = res["access_token"]
                self.ctx.tokens.set("threads", {"token": token, "refreshed_at": iso(utcnow()),
                                                "seed": self.secret("THREADS_ACCESS_TOKEN")})
            except ApiError as e:  # e.g. token younger than 24h — try again tomorrow
                log(f"threads token refresh failed: {e}", "warning")
                self.ctx.tokens.set("threads", {
                    "token": token, "seed": self.secret("THREADS_ACCESS_TOKEN"),
                    "refreshed_at": iso(utcnow() - self.REFRESH_EVERY + timedelta(days=1))})
        return token

    def _container(self, params: dict) -> str:
        uid = self.secret("THREADS_USER_ID")
        tok = self.token()
        cid = request("POST", f"{self.base}/{uid}/threads", self.name,
                      data={**params, "access_token": tok}).json()["id"]

        def ready():
            res = request("GET", f"{self.base}/{cid}", self.name,
                          params={"fields": "status,error_message", "access_token": tok}).json()
            if res.get("status") in ("ERROR", "EXPIRED"):
                raise ApiError(self.name, f"Threads couldn't process the media: {res.get('error_message')}")
            return res.get("status") in ("FINISHED", "PUBLISHED")

        self.wait_until(ready, "Threads to process the media", timeout=900, every=8)
        return cid

    def _item(self, rel: str, carousel: bool) -> dict:
        url = public_url(self.ctx.cfg, rel)
        is_image = rel.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
        params = {"media_type": "IMAGE", "image_url": url} if is_image else {"media_type": "VIDEO", "video_url": url}
        if carousel:
            params["is_carousel_item"] = "true"
        return params

    def publish(self, r: Rendered) -> dict:
        media = r.post.media
        if not media:
            cid = self._container({"media_type": "TEXT", "text": r.text})
        elif len(media) == 1:
            cid = self._container({**self._item(media[0], False), "text": r.text})
        else:
            children = [self._container(self._item(m, True)) for m in media[:20]]
            cid = self._container({"media_type": "CAROUSEL", "children": ",".join(children), "text": r.text})
        tok = self.token()
        tid = request("POST", f"{self.base}/{self.secret('THREADS_USER_ID')}/threads_publish", self.name,
                      data={"creation_id": cid, "access_token": tok}).json()["id"]
        url = request("GET", f"{self.base}/{tid}", self.name,
                      params={"fields": "permalink", "access_token": tok}).json().get("permalink")
        return {"id": tid, "url": url}

    def health(self) -> str:
        res = request("GET", f"{self.base}/me", self.name,
                      params={"fields": "username", "access_token": self.token()}).json()
        return f"@{res.get('username')}"
