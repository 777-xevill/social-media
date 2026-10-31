"""GitHub REST calls: alert issues (GitHub emails them to you) and workflow keep-alive."""
from __future__ import annotations

import os

from .net import ApiError, log, request, scrub

API = "https://api.github.com"
ALERT_LABEL = "bot-alert"


class GitHub:
    def __init__(self, token: str | None = None, repo: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.repo)

    def _call(self, method: str, path: str, **kw):
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json"}
        return request(method, f"{API}/repos/{self.repo}{path}", "github", headers=headers, **kw)

    def alert(self, title: str, body: str, label: str = ALERT_LABEL) -> str | None:
        """Comments on the open issue with this title, or opens a new one. Returns its URL."""
        body = scrub(body)
        if not self.enabled:
            log(f"[alert] {title}\n{body}", "warning")
            return None
        try:
            self._ensure_label(label)
            issues = self._call("GET", "/issues", params={"state": "open", "labels": label, "per_page": 50}).json()
            match = next((i for i in issues if i["title"] == title), None)
            if match:
                self._call("POST", f"/issues/{match['number']}/comments", json={"body": body})
                return match["html_url"]
            issue = self._call("POST", "/issues", json={"title": title, "body": body, "labels": [label]}).json()
            return issue["html_url"]
        except ApiError as e:
            log(f"could not open GitHub issue: {e}\n{title}\n{body}", "warning")
            return None

    def _ensure_label(self, label: str) -> None:
        try:
            self._call("GET", f"/labels/{label}")
        except ApiError:
            self._call("POST", "/labels", json={"name": label, "color": "d93f0b"})

    def enable_workflows(self, files: list[str]) -> None:
        """Re-enables scheduled workflows (GitHub pauses them after 60 days without activity)."""
        if not self.enabled:
            return
        for f in files:
            try:
                self._call("PUT", f"/actions/workflows/{f}/enable")
            except ApiError as e:
                log(f"keep-alive for {f} failed: {e}", "warning")
