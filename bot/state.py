"""Persistent bot state (state/state.json) and the encrypted token store (state/tokens.enc)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .config import STATE_DIR

TERMINAL = {"published", "skipped", "failed"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class State:
    def __init__(self, path: Path = STATE_DIR / "state.json"):
        self.path = path
        self.data: dict = {"version": 1, "posts": {}, "platform_last": {}, "last_tick": None}
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        _atomic_write(self.path, (json.dumps(self.data, indent=2, sort_keys=True) + "\n").encode())

    @property
    def posts(self) -> dict:
        return self.data["posts"]

    @property
    def platform_last(self) -> dict:
        return self.data["platform_last"]


class TokenStore:
    """Tokens the bot rotates itself (e.g. Threads), encrypted with TOKEN_STORE_KEY.

    GitHub's built-in token can't update repository secrets, so refreshed tokens are
    committed to the repo encrypted instead. Without the key nothing is stored.
    """

    def __init__(self, key: str | None, path: Path = STATE_DIR / "tokens.enc"):
        self.path = path
        self._fernet = Fernet(key.encode()) if key else None
        self._data: dict = {}
        self._dirty = False
        if self._fernet and path.exists():
            try:
                self._data = json.loads(self._fernet.decrypt(path.read_bytes()))
            except InvalidToken:
                self._data = {}  # key was changed — fall back to tokens from secrets

    @property
    def enabled(self) -> bool:
        return self._fernet is not None

    def get(self, name: str) -> dict | None:
        return self._data.get(name)

    def set(self, name: str, value: dict) -> None:
        self._data[name] = value
        self._dirty = True

    def save(self) -> None:
        if self._fernet and self._dirty:
            _atomic_write(self.path, self._fernet.encrypt(json.dumps(self._data).encode()))
            self._dirty = False
