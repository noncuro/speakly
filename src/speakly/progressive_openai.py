"""OpenAI TTS adapter for progressive chunk-by-chunk synthesis."""

from __future__ import annotations

import httpx

from speakly.providers.openai import OpenAIProvider, _get_api_key

OPENAI_CHUNK_MAX_CHARS = 3500


class OpenAIProgressiveAdapter:
    """Progressive adapter that synthesizes one OpenAI TTS MP3 chunk per call."""

    def max_chunk_chars(self) -> int:
        return OPENAI_CHUNK_MAX_CHARS

    def synthesize_chunk(self, text: str, voice: str, speed: float) -> bytes:
        voice = voice or OpenAIProvider.DEFAULT_VOICE
        speed = max(0.25, min(4.0, speed))
        api_key = _get_api_key()

        with httpx.Client(timeout=120) as client:
            response = client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "tts-1-hd",
                    "voice": voice,
                    "input": text,
                    "speed": speed,
                    "response_format": "mp3",
                },
            )
            response.raise_for_status()
            return response.content
