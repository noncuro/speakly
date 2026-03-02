"""Generic progressive TTS orchestration and chunking utilities."""

from __future__ import annotations

import random
import re
import shutil
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import httpx

PROGRESSIVE_MIN_CHARS = 800
FIRST_CHUNK_TARGET_CHARS = 320
NEXT_CHUNK_TARGET_CHARS = 1100
SHORT_SEGMENT_MERGE_CHARS = 120
PREFETCH_DEPTH = 2
LOW_WATERMARK = 1
MAX_WORKERS = 2
MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 0.5
RATE_LIMIT_FALLBACK_HITS = 2

_ABBREVIATIONS = {
    "dr.",
    "mr.",
    "mrs.",
    "ms.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
    "mt.",
    "vs.",
    "etc.",
    "e.g.",
    "i.e.",
    "u.s.",
    "u.k.",
    "no.",
    "fig.",
    "inc.",
    "ltd.",
    "co.",
}


class ProgressiveAdapter(Protocol):
    """Adapter for provider-specific chunk synthesis."""

    def max_chunk_chars(self) -> int:
        """Maximum safe input characters for one provider request."""
        ...

    def synthesize_chunk(self, text: str, voice: str, speed: float) -> bytes:
        """Synthesize one chunk and return MP3 bytes."""
        ...


@dataclass
class ProgressiveCallbacks:
    """Callbacks emitted by progressive generation."""

    on_chunk_ready: Callable[[Path], None]
    on_status: Callable[[str], None]
    on_done: Callable[[Path], None]
    on_error: Callable[[str], None]


@dataclass
class _SynthResult:
    index: int
    audio: bytes
    saw_rate_limit: bool


def split_sentence_aware(text: str) -> list[str]:
    """Split text on sentence/newline boundaries with abbreviation guards."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    segments: list[str] = []
    start = 0
    for i, ch in enumerate(text):
        if ch == "\n":
            _append_segment(segments, text[start : i + 1])
            start = i + 1
            continue
        if ch not in ".!?":
            continue
        if not _is_sentence_break(text, i):
            continue
        _append_segment(segments, text[start : i + 1])
        start = i + 1

    if start < len(text):
        _append_segment(segments, text[start:])

    return _merge_short_segments(segments, min_chars=SHORT_SEGMENT_MERGE_CHARS)


def build_chunks(
    text: str,
    first_target: int,
    next_target: int,
    max_chars: int,
) -> list[str]:
    """Build chunks from sentence-aware segments for progressive playback."""
    segments = split_sentence_aware(text)
    return pack_segments(
        segments=segments,
        first_target=first_target,
        next_target=next_target,
        max_chars=max_chars,
    )


def pack_segments(
    segments: list[str],
    first_target: int,
    next_target: int,
    max_chars: int,
) -> list[str]:
    """Pack sentence segments into size-targeted chunks."""
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for seg in segments:
        for part in _split_overlong_segment(seg, max_chars):
            target = first_target if not chunks else next_target
            if not current_parts:
                current_parts = [part]
                current_len = len(part)
                continue

            proposed = current_len + 1 + len(part)
            if proposed <= target or (current_len < int(target * 0.65) and proposed <= max_chars):
                current_parts.append(part)
                current_len = proposed
                continue

            chunks.append(" ".join(current_parts).strip())
            current_parts = [part]
            current_len = len(part)

    if current_parts:
        chunks.append(" ".join(current_parts).strip())

    return [c for c in chunks if c]


def merge_mp3_chunks(chunk_paths: list[Path], output_path: Path) -> Path:
    """Merge chunk MP3 files into one output file with boundary sanitization."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{output_path}.tmp")

    with open(tmp_path, "wb") as out:
        for i, chunk in enumerate(chunk_paths):
            data = chunk.read_bytes()
            if i > 0:
                data = strip_leading_id3(data)
            out.write(data)

    tmp_path.replace(output_path)
    return output_path


def strip_leading_id3(data: bytes) -> bytes:
    """Strip a leading ID3v2 tag if present."""
    if len(data) < 10 or not data.startswith(b"ID3"):
        return data

    size_bytes = data[6:10]
    tag_size = (
        ((size_bytes[0] & 0x7F) << 21)
        | ((size_bytes[1] & 0x7F) << 14)
        | ((size_bytes[2] & 0x7F) << 7)
        | (size_bytes[3] & 0x7F)
    )
    total_size = tag_size + 10
    if total_size >= len(data):
        return data
    return data[total_size:]


class ProgressiveOrchestrator:
    """Run chunked progressive synthesis and emit playback/caching callbacks."""

    def __init__(
        self,
        *,
        adapter: ProgressiveAdapter,
        text: str,
        voice: str,
        speed: float,
        output_path: Path,
        callbacks: ProgressiveCallbacks,
        first_target: int = FIRST_CHUNK_TARGET_CHARS,
        next_target: int = NEXT_CHUNK_TARGET_CHARS,
        prefetch_depth: int = PREFETCH_DEPTH,
        low_watermark: int = LOW_WATERMARK,
        max_workers: int = MAX_WORKERS,
        max_retries: int = MAX_RETRIES,
        backoff_base_seconds: float = BACKOFF_BASE_SECONDS,
    ):
        self.adapter = adapter
        self.text = text
        self.voice = voice
        self.speed = speed
        self.output_path = output_path
        self.callbacks = callbacks
        self.first_target = first_target
        self.next_target = next_target
        self.prefetch_depth = max(1, prefetch_depth)
        self.low_watermark = max(0, low_watermark)
        self.max_workers = max(1, max_workers)
        self.max_retries = max(0, max_retries)
        self.backoff_base_seconds = max(0.1, backoff_base_seconds)
        self.parts_dir = output_path.parent / "parts" / output_path.stem
        self.partial_path = output_path.with_suffix(".partial.mp3")

    def run(self) -> None:
        chunks = build_chunks(
            text=self.text,
            first_target=self.first_target,
            next_target=self.next_target,
            max_chars=self.adapter.max_chunk_chars(),
        )
        if not chunks:
            self.callbacks.on_error("No text chunks were produced.")
            return

        self.callbacks.on_status("streaming")
        self._prepare_parts_dir()

        emitted_paths: list[Path] = []
        pending: dict[Future[_SynthResult], int] = {}
        ready: dict[int, _SynthResult] = {}
        next_submit = 0
        next_emit = 0
        worker_limit = self.max_workers
        rate_limit_hits = 0
        fatal_error: Exception | None = None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while next_emit < len(chunks):
                backlog = next_submit - next_emit
                target_backlog = self.prefetch_depth + 1 if backlog <= self.low_watermark else self.prefetch_depth
                target_backlog = max(1, target_backlog)

                while (
                    next_submit < len(chunks)
                    and len(pending) < worker_limit
                    and (next_submit - next_emit) < target_backlog
                ):
                    fut = executor.submit(
                        self._synthesize_with_retries,
                        next_submit,
                        chunks[next_submit],
                    )
                    pending[fut] = next_submit
                    next_submit += 1

                if next_emit in ready:
                    emitted_path = self._emit_ready(next_emit, ready.pop(next_emit))
                    emitted_paths.append(emitted_path)
                    next_emit += 1
                    continue

                if not pending:
                    fatal_error = RuntimeError("Progressive generation stalled with no pending work.")
                    break

                done, _ = wait(tuple(pending.keys()), return_when=FIRST_COMPLETED)
                for fut in done:
                    pending.pop(fut, None)
                    try:
                        result = fut.result()
                    except Exception as exc:
                        fatal_error = exc
                        continue

                    if result.saw_rate_limit:
                        rate_limit_hits += 1
                        if rate_limit_hits >= RATE_LIMIT_FALLBACK_HITS and worker_limit > 1:
                            worker_limit = 1
                            self.callbacks.on_status("streaming (rate-limited)")

                    ready[result.index] = result

                if fatal_error:
                    for fut in pending:
                        fut.cancel()
                    pending.clear()
                    break

                while next_emit in ready:
                    emitted_path = self._emit_ready(next_emit, ready.pop(next_emit))
                    emitted_paths.append(emitted_path)
                    next_emit += 1

        if fatal_error is not None:
            self._handle_failure(fatal_error, emitted_paths)
            return

        if not emitted_paths:
            self.callbacks.on_error("No audio was generated.")
            return

        try:
            merge_mp3_chunks(emitted_paths, self.output_path)
        except Exception as exc:
            self._handle_failure(exc, emitted_paths)
            return

        shutil.rmtree(self.parts_dir, ignore_errors=True)
        self.callbacks.on_done(self.output_path)
        self.callbacks.on_status("complete")

    def _prepare_parts_dir(self) -> None:
        if self.parts_dir.exists():
            shutil.rmtree(self.parts_dir, ignore_errors=True)
        self.parts_dir.mkdir(parents=True, exist_ok=True)

    def _emit_ready(self, index: int, result: _SynthResult) -> Path:
        chunk_path = self.parts_dir / f"chunk{index:04d}.mp3"
        chunk_path.write_bytes(result.audio)
        self.callbacks.on_chunk_ready(chunk_path)
        return chunk_path

    def _synthesize_with_retries(self, index: int, text: str) -> _SynthResult:
        saw_rate_limit = False
        last_exc: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                audio = self.adapter.synthesize_chunk(text, self.voice, self.speed)
                return _SynthResult(index=index, audio=audio, saw_rate_limit=saw_rate_limit)
            except Exception as exc:  # noqa: PERF203 - retry loop
                last_exc = exc
                if _is_rate_limited(exc):
                    saw_rate_limit = True

                if attempt >= self.max_retries or not _is_retryable(exc):
                    raise

                delay = self.backoff_base_seconds * (2**attempt) + random.uniform(0.0, 0.15)
                time.sleep(delay)

        raise RuntimeError("retry loop ended unexpectedly") from last_exc

    def _handle_failure(self, exc: Exception, emitted_paths: list[Path]) -> None:
        if emitted_paths:
            try:
                merge_mp3_chunks(emitted_paths, self.partial_path)
            except Exception:
                pass
        self.callbacks.on_error(_format_exception(exc))


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


def _is_rate_limited(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _format_exception(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in {401, 403}:
            return "Authentication failed for Inworld credentials."
        return f"HTTP {code} from TTS provider."
    return str(exc)


def _append_segment(out: list[str], raw: str) -> None:
    clean = " ".join(raw.split())
    if clean:
        out.append(clean)


def _merge_short_segments(segments: list[str], min_chars: int) -> list[str]:
    if not segments:
        return []

    def is_tiny(seg: str) -> bool:
        # Merge only very short fragments, not complete short sentences.
        return (
            len(seg) < min_chars
            and len(seg.split()) <= 3
            and not seg.endswith((".", "!", "?"))
        )

    merged: list[str] = []
    for seg in segments:
        if merged and is_tiny(seg):
            merged[-1] = f"{merged[-1]} {seg}".strip()
        else:
            merged.append(seg)

    if len(merged) > 1 and is_tiny(merged[0]):
        merged[1] = f"{merged[0]} {merged[1]}".strip()
        merged = merged[1:]

    return merged


def _is_sentence_break(text: str, index: int) -> bool:
    ch = text[index]
    if ch == "." and _is_decimal_point(text, index):
        return False

    token = _token_before(text, index)
    if token.lower() in _ABBREVIATIONS:
        return False
    if re.fullmatch(r"(?:[A-Z]\.){2,}", token):
        return False
    if re.fullmatch(r"[A-Z]\.", token):
        return False

    j = index + 1
    while j < len(text) and text[j] in "\"')]}":
        j += 1
    if j < len(text) and not text[j].isspace():
        return False
    return True


def _token_before(text: str, index: int) -> str:
    start = index
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    return text[start : index + 1]


def _is_decimal_point(text: str, index: int) -> bool:
    return (
        index > 0
        and index + 1 < len(text)
        and text[index] == "."
        and text[index - 1].isdigit()
        and text[index + 1].isdigit()
    )


def _split_overlong_segment(segment: str, max_chars: int) -> list[str]:
    if len(segment) <= max_chars:
        return [segment]

    parts: list[str] = []
    text = segment
    while text:
        if len(text) <= max_chars:
            parts.append(text.strip())
            break

        cut = text[:max_chars].rfind(" ")
        if cut < 1:
            cut = max_chars
        parts.append(text[:cut].strip())
        text = text[cut:].strip()

    return [p for p in parts if p]
