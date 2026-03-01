"""Audio file caching for TTS output."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

CACHE_DIR = Path.home() / ".speakly" / "cache"
MAX_AGE_DAYS = 7


def cache_key(text: str, provider: str, voice: str) -> str:
    content = f"{provider}:{voice}:{text}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_cached(text: str, provider: str, voice: str) -> Path | None:
    key = cache_key(text, provider, voice)
    path = CACHE_DIR / f"{key}.mp3"
    if path.exists():
        return path
    return None


def cache_path(text: str, provider: str, voice: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = cache_key(text, provider, voice)
    return CACHE_DIR / f"{key}.mp3"


def evict_old():
    if not CACHE_DIR.exists():
        return
    cutoff = time.time() - (MAX_AGE_DAYS * 86400)
    for f in CACHE_DIR.glob("*.mp3"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
