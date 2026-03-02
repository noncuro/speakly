from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from speakly.progressive_core import (
    ProgressiveCallbacks,
    ProgressiveOrchestrator,
    build_chunks,
    split_sentence_aware,
    strip_leading_id3,
)


class FakeAdapter:
    def __init__(self, fail_after: int | None = None, delay: float = 0.0):
        self.calls = 0
        self.fail_after = fail_after
        self.delay = delay

    def max_chunk_chars(self) -> int:
        return 200

    def synthesize_chunk(self, text: str, voice: str, speed: float) -> bytes:
        del voice, speed
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("simulated failure")
        return f"MP3:{text}".encode()


class ProgressiveCoreTests(unittest.TestCase):
    def test_sentence_split_handles_abbrev_and_decimals(self):
        text = (
            "Dr. Smith paid $3.14 for lunch. Mr. Jones said e.g. examples help. "
            "The U.S. team won! Final line?"
        )
        segments = split_sentence_aware(text)
        self.assertGreaterEqual(len(segments), 3)
        self.assertIn("Dr. Smith paid $3.14 for lunch.", segments[0])
        self.assertTrue(any("U.S. team won!" in s for s in segments))

    def test_build_chunks_respects_max_chars(self):
        text = (
            "Sentence one is moderately long and should stay intact. "
            "Sentence two is another segment to pack. "
            "Sentence three adds enough material for more than one chunk."
        )
        chunks = build_chunks(text, first_target=40, next_target=60, max_chars=80)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 80 for chunk in chunks))

    def test_strip_leading_id3(self):
        tag_size = 4
        synchsafe = bytes([0, 0, 0, tag_size])
        header = b"ID3" + bytes([4, 0, 0]) + synchsafe
        data = header + b"ABCD" + b"MP3DATA"
        stripped = strip_leading_id3(data)
        self.assertEqual(stripped, b"MP3DATA")

    def test_orchestrator_emits_chunk_before_done(self):
        events: list[str] = []
        output_path = Path(tempfile.mkdtemp()) / "out.mp3"
        adapter = FakeAdapter(delay=0.02)
        callbacks = ProgressiveCallbacks(
            on_chunk_ready=lambda p: events.append(f"chunk:{p.name}"),
            on_status=lambda s: events.append(f"status:{s}"),
            on_done=lambda p: events.append(f"done:{p.name}"),
            on_error=lambda e: events.append(f"error:{e}"),
        )
        orchestrator = ProgressiveOrchestrator(
            adapter=adapter,
            text="One sentence. Two sentence. Three sentence. Four sentence.",
            voice="",
            speed=1.0,
            output_path=output_path,
            callbacks=callbacks,
            first_target=10,
            next_target=10,
            max_workers=2,
        )
        orchestrator.run()

        chunk_idx = next(i for i, event in enumerate(events) if event.startswith("chunk:"))
        done_idx = next(i for i, event in enumerate(events) if event.startswith("done:"))
        self.assertLess(chunk_idx, done_idx)
        self.assertTrue(output_path.exists())

    def test_orchestrator_writes_partial_on_failure(self):
        errors: list[str] = []
        root = Path(tempfile.mkdtemp())
        output_path = root / "out.mp3"
        partial_path = root / "out.partial.mp3"
        adapter = FakeAdapter(fail_after=1)
        callbacks = ProgressiveCallbacks(
            on_chunk_ready=lambda p: None,
            on_status=lambda s: None,
            on_done=lambda p: None,
            on_error=lambda e: errors.append(e),
        )
        orchestrator = ProgressiveOrchestrator(
            adapter=adapter,
            text="One sentence. Two sentence. Three sentence.",
            voice="",
            speed=1.0,
            output_path=output_path,
            callbacks=callbacks,
            first_target=12,
            next_target=12,
            max_workers=1,
        )
        orchestrator.run()

        self.assertFalse(output_path.exists())
        self.assertTrue(partial_path.exists())
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
