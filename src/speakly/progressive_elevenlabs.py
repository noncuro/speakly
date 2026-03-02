"""ElevenLabs TTS adapter for progressive chunk-by-chunk synthesis."""

from __future__ import annotations

import httpx

from speakly.providers.elevenlabs import API_BASE, ElevenLabsProvider

ELEVENLABS_CHUNK_MAX_CHARS = 2500


class ElevenLabsProgressiveAdapter:
    """Progressive adapter that synthesizes one ElevenLabs MP3 chunk per call."""

    def __init__(self):
        self._provider = ElevenLabsProvider()
        if not self._provider._api_key:
            raise ValueError(
                "ELEVEN_API_KEY not set. Run 'speakly config' or set the environment variable."
            )
        self._voice_id_cache: dict[str, str] = {}

    def max_chunk_chars(self) -> int:
        return ELEVENLABS_CHUNK_MAX_CHARS

    def synthesize_chunk(self, text: str, voice: str, speed: float) -> bytes:
        del speed  # ElevenLabs has no native speed parameter; use player speed.
        voice_id = self._resolve_voice_id(voice)

        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{API_BASE}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self._provider._api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            )
            response.raise_for_status()
            return response.content

    def _resolve_voice_id(self, voice: str) -> str:
        selected = (voice or self._provider.DEFAULT_VOICE).strip()
        if selected in self._voice_id_cache:
            return self._voice_id_cache[selected]
        if self._provider._looks_like_id(selected):
            self._voice_id_cache[selected] = selected
            return selected

        voice_id = self._provider._resolve_voice_name(selected)
        self._voice_id_cache[selected] = voice_id
        return voice_id
