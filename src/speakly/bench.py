"""Lightweight benchmarking instrumentation for Speakly.

Enable with SPEAKLY_BENCH=1. All functions are no-ops when disabled.
"""

from __future__ import annotations

import json
import os
import sys
import time

_ENABLED = bool(os.environ.get("SPEAKLY_BENCH"))
_T0 = time.perf_counter()
_FIRST_AUDIO_T: float | None = None


def enabled() -> bool:
    return _ENABLED


def elapsed() -> float:
    """Seconds since module load (process start proxy)."""
    return time.perf_counter() - _T0


def mark(event: str, **extra: object) -> float:
    """Log a timestamped event to stderr. Returns elapsed time. No-op when disabled."""
    t = time.perf_counter() - _T0
    if not _ENABLED:
        return t
    parts = [f"[bench] {t:7.3f}s  {event}"]
    for k, v in extra.items():
        parts.append(f"{k}={v}")
    print("  ".join(parts), file=sys.stderr, flush=True)
    return t


def mark_first_audio() -> float:
    """Record time-to-first-audio (only first call counts). Returns elapsed time."""
    global _FIRST_AUDIO_T
    t = time.perf_counter() - _T0
    if _FIRST_AUDIO_T is None:
        _FIRST_AUDIO_T = t
    if _ENABLED:
        mark("first_audio")
    return t


def get_first_audio_time() -> float | None:
    return _FIRST_AUDIO_T


def summary_json(**fields: object) -> str:
    """Emit machine-parseable JSON summary line to stderr."""
    if not _ENABLED:
        return ""
    line = json.dumps({"bench_summary": True, **fields})
    print(line, file=sys.stderr, flush=True)
    return line
