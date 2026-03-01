"""ElevenLabs TTS provider."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from . import TTSProvider, Voice, register

API_BASE = "https://api.elevenlabs.io/v1"


@register("elevenlabs")
class ElevenLabsProvider:
    name = "elevenlabs"

    # Popular default voices
    DEFAULT_VOICE = "Rachel"
    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

    def __init__(self):
        self._api_key = os.environ.get("ELEVEN_API_KEY", "")

    def synthesize(self, text: str, voice: str, speed: float, output_path: Path) -> Path:
        voice_id = voice if self._looks_like_id(voice) else self._resolve_voice_name(voice)

        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{API_BASE}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self._api_key,
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
            output_path.write_bytes(response.content)

        return output_path

    def _looks_like_id(self, voice: str) -> bool:
        return len(voice) > 15 and voice.isalnum()

    def _resolve_voice_name(self, name: str) -> str:
        if not name or name.lower() == "rachel":
            return self.DEFAULT_VOICE_ID
        # Try to find voice by name
        voices = self._fetch_voices()
        for v in voices:
            if v["name"].lower() == name.lower():
                return v["voice_id"]
        raise ValueError(f"ElevenLabs voice '{name}' not found")

    def _fetch_voices(self) -> list[dict]:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{API_BASE}/voices",
                headers={"xi-api-key": self._api_key},
            )
            resp.raise_for_status()
            return resp.json()["voices"]

    def list_voices(self) -> list[Voice]:
        voices = self._fetch_voices()
        return [
            Voice(id=v["voice_id"], name=v["name"], provider=self.name)
            for v in voices
        ]
