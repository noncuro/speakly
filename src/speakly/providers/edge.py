"""Microsoft Edge TTS provider."""

from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from . import TTSProvider, Voice, register

DEFAULT_VOICE = "en-US-AriaNeural"


@register("edge")
class EdgeProvider:
    name = "edge"

    def synthesize(self, text: str, voice: str, speed: float, output_path: Path) -> Path:
        voice = voice or DEFAULT_VOICE
        communicate = edge_tts.Communicate(text, voice)
        asyncio.run(communicate.save(str(output_path)))
        return output_path

    def list_voices(self) -> list[Voice]:
        all_voices = asyncio.run(edge_tts.list_voices())
        return [
            Voice(id=v["ShortName"], name=v["FriendlyName"], provider=self.name)
            for v in all_voices
            if v.get("Locale", "").startswith("en")
        ]
