from __future__ import annotations

import time
from dataclasses import dataclass

from ..config import Config, Secrets
from ..content import Rendered
from ..github import GitHub
from ..net import ApiError
from ..state import TokenStore


@dataclass
class Context:
    cfg: Config
    secrets: Secrets
    tokens: TokenStore
    github: GitHub


class Adapter:
    name = ""
    secrets_needed: tuple[str, ...] = ()
    supports = {"text", "image", "images", "video", "mixed"}
    setup_hint = "see SETUP.md"

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.pcfg = ctx.cfg.platform(self.name)

    def secret(self, key: str) -> str | None:
        return self.ctx.secrets.get(key)

    def missing_secrets(self) -> list[str]:
        return self.ctx.secrets.missing(*self.secrets_needed)

    KIND_NAMES = {"text": "text-only", "image": "image", "images": "multi-image",
                  "video": "video", "mixed": "mixed photo+video"}

    def incompatible(self, r: Rendered) -> str | None:
        if r.post.kind not in self.supports:
            return f"{self.name} doesn't take {self.KIND_NAMES[r.post.kind]} posts"
        return None

    def publish(self, r: Rendered) -> dict:
        """Posts and returns {'id': ..., 'url': ...}."""
        raise NotImplementedError

    def health(self) -> str:
        """Cheap call proving the credentials still work. Returns account name/info."""
        return "configured"

    def wait_until(self, check, what: str, timeout: int = 600, every: int = 10):
        """Polls `check()` until it returns a truthy value."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = check()
            if result:
                return result
            time.sleep(every)
        raise ApiError(self.name, f"timed out waiting for {what}")
