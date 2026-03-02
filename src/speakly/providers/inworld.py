"""Inworld TTS provider."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import httpx

from . import TTSProvider, Voice, register

API_BASE = "https://api.inworld.ai"
MAX_CHARS = 2000


@register("inworld")
class InworldProvider:
    name = "inworld"

    DEFAULT_VOICE = "Alex"

    def __init__(self):
        try:
            from speakly.config import get_api_key
            self._jwt_key = get_api_key("INWORLD_JWT_KEY") or ""
            self._jwt_secret = get_api_key("INWORLD_JWT_SECRET") or ""
        except Exception:
            self._jwt_key = os.environ.get("INWORLD_JWT_KEY", "")
            self._jwt_secret = os.environ.get("INWORLD_JWT_SECRET", "")

    def _get_auth_header(self) -> str:
        credentials = f"{self._jwt_key}:{self._jwt_secret}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def synthesize(self, text: str, voice: str, speed: float, output_path: Path) -> Path:
        voice = voice or self.DEFAULT_VOICE

        # Resolve voice name to ID if needed
        voice_id = voice
        if not voice.startswith("voice_"):
            voice_id = self._resolve_voice_name(voice)

        chunks = self._chunk_text(text)
        if len(chunks) == 1:
            self._generate_chunk(chunks[0], voice_id, output_path)
        else:
            chunk_paths = []
            for i, chunk in enumerate(chunks):
                chunk_path = output_path.with_suffix(f".chunk{i}.mp3")
                self._generate_chunk(chunk, voice_id, chunk_path)
                chunk_paths.append(chunk_path)
            with open(output_path, "wb") as out:
                for p in chunk_paths:
                    out.write(p.read_bytes())
            for p in chunk_paths:
                p.unlink(missing_ok=True)

        return output_path

    def _generate_chunk(self, text: str, voice_id: str, path: Path) -> None:
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{API_BASE}/tts/v1/voice",
                headers={
                    "Authorization": self._get_auth_header(),
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "voiceId": voice_id,
                    "modelId": "inworld-tts-1.5-max",
                    "audioConfig": {
                        "audioEncoding": "MP3",
                    },
                },
            )
            response.raise_for_status()
            audio_data = response.json().get("audioContent", "")
            path.write_bytes(base64.b64decode(audio_data))

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= MAX_CHARS:
            return [text]
        chunks = []
        while text:
            if len(text) <= MAX_CHARS:
                chunks.append(text)
                break
            cut = text[:MAX_CHARS].rfind(". ")
            if cut == -1:
                cut = text[:MAX_CHARS].rfind(" ")
            if cut == -1:
                cut = MAX_CHARS
            else:
                cut += 1
            chunks.append(text[:cut].strip())
            text = text[cut:].strip()
        return chunks

    def _resolve_voice_name(self, name: str) -> str:
        voices = self._fetch_voices()
        for v in voices:
            if v["displayName"].lower() == name.lower():
                return v["voiceId"]
        raise ValueError(f"Inworld voice '{name}' not found. Available: {[v['displayName'] for v in voices]}")

    def _fetch_voices(self) -> list[dict]:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{API_BASE}/tts/v1/voices",
                headers={"Authorization": self._get_auth_header()},
                params={"filter": "language=en"},
            )
            resp.raise_for_status()
            return resp.json().get("voices", [])

    def list_voices(self) -> list[Voice]:
        voices = self._fetch_voices()
        return [
            Voice(id=v["voiceId"], name=v["displayName"], provider=self.name)
            for v in voices
        ]
