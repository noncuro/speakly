"""Edge TTS adapter for progressive chunk-by-chunk synthesis."""

from __future__ import annotations

import asyncio

import edge_tts

from speakly.providers.edge import DEFAULT_VOICE

EDGE_CHUNK_MAX_CHARS = 3000


class EdgeProgressiveAdapter:
    """Progressive adapter that synthesizes one Edge TTS MP3 chunk per call."""

    def max_chunk_chars(self) -> int:
        return EDGE_CHUNK_MAX_CHARS

    def synthesize_chunk(self, text: str, voice: str, speed: float) -> bytes:
        del speed  # Edge TTS has no native speed parameter; use player speed.
        voice = voice or DEFAULT_VOICE
        return asyncio.run(self._stream_to_bytes(text, voice))

    @staticmethod
    async def _stream_to_bytes(text: str, voice: str) -> bytes:
        communicate = edge_tts.Communicate(text, voice)
        audio_parts: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_parts.append(chunk["data"])
        return b"".join(audio_parts)
