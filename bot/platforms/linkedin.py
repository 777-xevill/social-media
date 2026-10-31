"""LinkedIn personal profile via the free "Share on LinkedIn" product (Posts API)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from ..content import Rendered
from ..net import ApiError, request
from ..state import utcnow
from .base import Adapter

API = "https://api.linkedin.com/rest"


def little_text(text: str) -> str:
    """Escapes LinkedIn's reserved characters; turns #words into real hashtags."""
    out = []
    for part in re.split(r"(?<![\w/])(#\w+)", text):
        if re.fullmatch(r"#\w+", part):
            out.append("{hashtag|\\#|" + part[1:] + "}")
        else:
            out.append(re.sub(r"([\\|{}@\[\]()<>#*_~])", r"\\\1", part))
    return "".join(out)


def _recent_versions(n: int = 12) -> list[str]:
    """LinkedIn-Version values to try, newest first (each version lives ~1 year)."""
    now = utcnow()
    y, m = now.year, now.month
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}{m:02d}")
    return out


class LinkedIn(Adapter):
    name = "linkedin"
    secrets_needed = ("LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN")
    supports = {"text", "image", "images", "video"}
    setup_hint = "run `python -m bot auth linkedin` (LinkedIn tokens last 60 days)"
    _version: str | None = None

    @property
    def token(self) -> str:
        return self.secret("LINKEDIN_ACCESS_TOKEN")

    def call(self, method: str, path: str, **kw):
        for version in [self._version] if self._version else _recent_versions():
            headers = {"Authorization": f"Bearer {self.token}", "LinkedIn-Version": version,
                       "X-Restli-Protocol-Version": "2.0.0"}
            try:
                res = request(method, f"{API}{path}", self.name, headers=headers, **kw)
            except ApiError as e:
                if e.status in (400, 426) and "version" in str(e).lower():
                    continue
                raise
            LinkedIn._version = version
            return res
        raise ApiError(self.name, "no active LinkedIn-Version found")

    def _upload_image(self, path) -> str:
        init = self.call("POST", "/images?action=initializeUpload", json={
            "initializeUploadRequest": {"owner": self.secret("LINKEDIN_PERSON_URN")}}).json()["value"]
        with open(path, "rb") as f:
            request("PUT", init["uploadUrl"], self.name, data=f, timeout=600,
                    headers={"Authorization": f"Bearer {self.token}"})
        return init["image"]

    def _upload_video(self, path) -> str:
        init = self.call("POST", "/videos?action=initializeUpload", json={"initializeUploadRequest": {
            "owner": self.secret("LINKEDIN_PERSON_URN"), "fileSizeBytes": path.stat().st_size,
            "uploadCaptions": False, "uploadThumbnail": False}}).json()["value"]
        etags = []
        with open(path, "rb") as f:
            for part in init["uploadInstructions"]:
                f.seek(part["firstByte"])
                chunk = f.read(part["lastByte"] - part["firstByte"] + 1)
                res = request("PUT", part["uploadUrl"], self.name, data=chunk, timeout=600,
                              headers={"Content-Type": "application/octet-stream"})
                etags.append(res.headers.get("ETag"))
        video = init["video"]
        self.call("POST", "/videos?action=finalizeUpload", json={"finalizeUploadRequest": {
            "video": video, "uploadToken": init.get("uploadToken", ""), "uploadedPartIds": etags}})

        def ready():
            status = self.call("GET", f"/videos/{quote(video)}").json().get("status")
            if status == "PROCESSING_FAILED":
                raise ApiError(self.name, "LinkedIn couldn't process the video")
            return status == "AVAILABLE"

        self.wait_until(ready, "LinkedIn to process the video", timeout=900)
        return video

    def publish(self, r: Rendered) -> dict:
        text, content = r.text, None
        kind = r.post.kind
        if kind == "text" and r.link:
            content = {"article": {"source": r.link, "title": r.title[:200]}}
        elif kind == "image":
            content = {"media": {"id": self._upload_image(r.media_paths[0]), "altText": r.post.alt[:4086]}}
        elif kind == "images":
            content = {"multiImage": {"images": [
                {"id": self._upload_image(p), "altText": ""} for p in r.media_paths[:20]]}}
        elif kind == "video":
            content = {"media": {"id": self._upload_video(r.media_paths[0]), "title": r.title[:200]}}
        body = {
            "author": self.secret("LINKEDIN_PERSON_URN"), "commentary": little_text(text),
            "visibility": "PUBLIC", "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False,
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                             "thirdPartyDistributionChannels": []},
        }
        if content:
            body["content"] = content
        urn = self.call("POST", "/posts", json=body).headers.get("x-restli-id", "")
        return {"id": urn, "url": f"https://www.linkedin.com/feed/update/{urn}"}

    def expires_at(self) -> datetime | None:
        """When the access token dies (needs the client id/secret to ask LinkedIn)."""
        if not self.ctx.secrets.has("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"):
            return None
        res = request("POST", "https://www.linkedin.com/oauth/v2/introspectToken", self.name, data={
            "client_id": self.secret("LINKEDIN_CLIENT_ID"),
            "client_secret": self.secret("LINKEDIN_CLIENT_SECRET"), "token": self.token}).json()
        if not res.get("active"):
            raise ApiError(self.name, "LinkedIn access token has expired", auth=True)
        return datetime.fromtimestamp(res["expires_at"], timezone.utc) if res.get("expires_at") else None

    def health(self) -> str:
        res = request("GET", "https://api.linkedin.com/v2/userinfo", self.name,
                      headers={"Authorization": f"Bearer {self.token}"}).json()
        return f"profile: {res.get('name')}"
