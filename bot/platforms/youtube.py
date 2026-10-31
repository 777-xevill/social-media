from __future__ import annotations

import re

from ..content import Rendered
from ..media import mime
from ..net import ApiError, log, request
from .base import Adapter

TOKEN_URL = "https://oauth2.googleapis.com/token"


class YouTube(Adapter):
    name = "youtube"
    secrets_needed = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    supports = {"video"}
    setup_hint = "run `python -m bot auth youtube`"

    def access_token(self) -> str:
        try:
            return request("POST", TOKEN_URL, self.name, data={
                "client_id": self.secret("YOUTUBE_CLIENT_ID"),
                "client_secret": self.secret("YOUTUBE_CLIENT_SECRET"),
                "refresh_token": self.secret("YOUTUBE_REFRESH_TOKEN"),
                "grant_type": "refresh_token",
            }).json()["access_token"]
        except ApiError as e:
            raise ApiError(self.name, f"Google refused the refresh token ({e}). If your OAuth app is in "
                           "'Testing' mode tokens die after 7 days — publish it to 'In production'.",
                           e.status, auth=True) from e

    def publish(self, r: Rendered) -> dict:
        token = self.access_token()
        path = r.media_paths[0]
        clean = lambda s: re.sub(r"[<>]", "", s)  # YouTube rejects angle brackets
        title = clean(r.title)[:100]
        description = clean(r.text)
        if r.is_short and "#shorts" not in (title + description).lower():
            description = f"{description}\n\n#Shorts".strip()
        privacy = self.pcfg.get("privacy", "public")
        body = {
            "snippet": {"title": title, "description": description[:5000],
                        "tags": r.post.hashtags[:15], "categoryId": str(self.pcfg.get("category_id", "22"))},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
        }
        init = request("POST", "https://www.googleapis.com/upload/youtube/v3/videos", self.name,
                       params={"uploadType": "resumable", "part": "snippet,status"}, json=body,
                       headers={"Authorization": f"Bearer {token}",
                                "X-Upload-Content-Length": str(path.stat().st_size),
                                "X-Upload-Content-Type": mime(path)})
        with open(path, "rb") as f:
            res = request("PUT", init.headers["Location"], self.name, data=f, timeout=1800,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": mime(path)}).json()
        vid = res["id"]
        actual = (res.get("status") or {}).get("privacyStatus")
        if actual and actual != privacy:
            log(f"YouTube made video {vid} '{actual}' instead of '{privacy}'. Unaudited Google API projects "
                "can only upload private videos — see SETUP.md › YouTube › audit.", "warning")
        url = f"https://www.youtube.com/shorts/{vid}" if r.is_short else f"https://youtu.be/{vid}"
        return {"id": vid, "url": url}

    def health(self) -> str:
        res = request("GET", "https://www.googleapis.com/youtube/v3/channels", self.name,
                      params={"part": "snippet", "mine": "true"},
                      headers={"Authorization": f"Bearer {self.access_token()}"}).json()
        items = res.get("items") or []
        return f"channel: {items[0]['snippet']['title']}" if items else "no channel on this Google account"
