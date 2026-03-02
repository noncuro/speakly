"""Inworld adapter for progressive chunk-by-chunk synthesis."""

from __future__ import annotations

import base64

import httpx

from speakly.providers.inworld import API_BASE, MAX_CHARS, InworldProvider

INWORLD_CHUNK_MAX_CHARS = 1800


class InworldProgressiveAdapter:
    """Progressive adapter that emits one Inworld MP3 chunk per request."""

    def __init__(self):
        self._provider = InworldProvider()
        if not self._provider._jwt_key or not self._provider._jwt_secret:
            raise ValueError(
                "INWORLD_JWT_KEY/INWORLD_JWT_SECRET not set. Run 'speakly config' to configure them."
            )
        self._voice_id_cache: dict[str, str] = {}

    def max_chunk_chars(self) -> int:
        return min(INWORLD_CHUNK_MAX_CHARS, MAX_CHARS)

    def synthesize_chunk(self, text: str, voice: str, speed: float) -> bytes:
        del speed  # Inworld model currently ignores native speed control.
        voice_id = self._resolve_voice_id(voice)

        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{API_BASE}/tts/v1/voice",
                headers={
                    "Authorization": self._provider._get_auth_header(),
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "voiceId": voice_id,
                    "modelId": "inworld-tts-1.5-max",
                    "audioConfig": {"audioEncoding": "MP3"},
                },
            )

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {401, 403}:
                    raise ValueError(
                        "Inworld auth failed. Check INWORLD_JWT_KEY and INWORLD_JWT_SECRET."
                    ) from exc
                raise

            audio_data = response.json().get("audioContent", "")
            if not audio_data:
                raise ValueError("Inworld response was missing audioContent.")
            return base64.b64decode(audio_data)

    def _resolve_voice_id(self, voice: str) -> str:
        selected = (voice or self._provider.DEFAULT_VOICE).strip()
        if selected in self._voice_id_cache:
            return self._voice_id_cache[selected]
        if selected.startswith("voice_"):
            self._voice_id_cache[selected] = selected
            return selected

        voice_id = self._provider._resolve_voice_name(selected)
        self._voice_id_cache[selected] = voice_id
        return voice_id
