"""OpenAI TTS provider."""

from __future__ import annotations

from pathlib import Path

import httpx

from . import Voice, register

MAX_CHARS = 4096


def _get_api_key() -> str:
    """Resolve OpenAI API key from env or keyring."""
    try:
        from speakly.config import get_api_key

        key = get_api_key("OPENAI_API_KEY")
    except Exception:
        import os

        key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "OPENAI_API_KEY not set. Run 'speakly config' or set the environment variable."
        )
    return key


@register("openai")
class OpenAIProvider:
    name = "openai"

    VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"]
    DEFAULT_VOICE = "nova"

    def synthesize(self, text: str, voice: str, speed: float, output_path: Path) -> Path:
        voice = voice or self.DEFAULT_VOICE
        # OpenAI supports speed 0.25-4.0
        speed = max(0.25, min(4.0, speed))

        chunks = self._chunk_text(text)
        if len(chunks) == 1:
            self._generate_chunk(chunks[0], voice, speed, output_path)
        else:
            chunk_paths = []
            for i, chunk in enumerate(chunks):
                chunk_path = output_path.with_suffix(f".chunk{i}.mp3")
                self._generate_chunk(chunk, voice, speed, chunk_path)
                chunk_paths.append(chunk_path)
            with open(output_path, "wb") as out:
                for p in chunk_paths:
                    out.write(p.read_bytes())
            for p in chunk_paths:
                p.unlink(missing_ok=True)

        return output_path

    def _generate_chunk(self, text: str, voice: str, speed: float, path: Path) -> None:
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
            path.write_bytes(response.content)

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

    def list_voices(self) -> list[Voice]:
        return [Voice(id=v, name=v.title(), provider=self.name) for v in self.VOICES]
