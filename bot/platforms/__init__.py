from __future__ import annotations

from ..config import PLATFORMS
from .base import Adapter, Context
from .linkedin import LinkedIn
from .meta import Facebook, Instagram, Threads
from .others import Buffer, Pinterest, Reddit, Snapchat, Unsupported
from .youtube import YouTube

DIRECT = {
    "facebook": Facebook, "instagram": Instagram, "threads": Threads, "youtube": YouTube,
    "linkedin": LinkedIn, "pinterest": Pinterest, "reddit": Reddit, "snapchat": Snapchat,
}


def build(ctx: Context) -> dict[str, Adapter]:
    adapters: dict[str, Adapter] = {}
    for name in PLATFORMS:
        via = ctx.cfg.platform(name)["via"]
        if via == "buffer":
            adapters[name] = Buffer(ctx, name)
        elif name in DIRECT:
            adapters[name] = DIRECT[name](ctx)
        else:
            adapters[name] = Unsupported(ctx, name)
    return adapters


__all__ = ["Adapter", "Context", "build"]
