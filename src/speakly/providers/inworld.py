"""Inworld TTS 1.5 provider."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx

from . import TTSProvider, Voice, register

API_BASE = "https://studio.inworld.ai/v1alpha"


@register("inworld")
class InworldProvider:
    name = "inworld"

    # Inworld voice presets
    VOICES = ["en-US-Standard-A", "en-US-Standard-B", "en-US-Standard-C", "en-US-Standard-D"]
    DEFAULT_VOICE = "en-US-Standard-A"

    def __init__(self):
        self._jwt_key = os.environ.get("INWORLD_JWT_KEY", "")
        self._jwt_secret = os.environ.get("INWORLD_JWT_SECRET", "")

    def _get_auth_header(self) -> str:
        credentials = f"{self._jwt_key}:{self._jwt_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def synthesize(self, text: str, voice: str, speed: float, output_path: Path) -> Path:
        voice = voice or self.DEFAULT_VOICE
        # Inworld supports speakingRate 0.5-1.5
        speaking_rate = max(0.5, min(1.5, speed))

        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{API_BASE}/tts:synthesize",
                headers={
                    "Authorization": self._get_auth_header(),
                    "Content-Type": "application/json",
                },
                json={
                    "input": {"text": text},
                    "voice": {
                        "name": voice,
                        "speakingRate": speaking_rate,
                    },
                    "audioConfig": {
                        "audioEncoding": "MP3",
                    },
                },
            )
            response.raise_for_status()
            audio_data = response.json().get("audioContent", "")
            output_path.write_bytes(base64.b64decode(audio_data))

        return output_path

    def list_voices(self) -> list[Voice]:
        return [Voice(id=v, name=v, provider=self.name) for v in self.VOICES]
