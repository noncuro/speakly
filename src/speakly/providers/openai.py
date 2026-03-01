"""OpenAI TTS provider."""

from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI

from . import TTSProvider, Voice, register

MAX_CHARS = 4096


@register("openai")
class OpenAIProvider:
    name = "openai"

    VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"]
    DEFAULT_VOICE = "nova"

    def __init__(self):
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def synthesize(self, text: str, voice: str, speed: float, output_path: Path) -> Path:
        voice = voice or self.DEFAULT_VOICE
        # OpenAI supports speed 0.25-4.0
        speed = max(0.25, min(4.0, speed))

        chunks = self._chunk_text(text)
        if len(chunks) == 1:
            self._generate_chunk(chunks[0], voice, speed, output_path)
        else:
            # Generate each chunk and concatenate
            chunk_paths = []
            for i, chunk in enumerate(chunks):
                chunk_path = output_path.with_suffix(f".chunk{i}.mp3")
                self._generate_chunk(chunk, voice, speed, chunk_path)
                chunk_paths.append(chunk_path)
            self._concatenate_mp3s(chunk_paths, output_path)
            for p in chunk_paths:
                p.unlink(missing_ok=True)

        return output_path

    def _generate_chunk(self, text: str, voice: str, speed: float, path: Path) -> None:
        response = self._client.audio.speech.create(
            model="tts-1-hd",
            voice=voice,
            input=text,
            speed=speed,
            response_format="mp3",
        )
        response.stream_to_file(str(path))

    def _chunk_text(self, text: str) -> list[str]:
        if len(text) <= MAX_CHARS:
            return [text]
        chunks = []
        while text:
            if len(text) <= MAX_CHARS:
                chunks.append(text)
                break
            # Find last sentence boundary before limit
            cut = text[:MAX_CHARS].rfind(". ")
            if cut == -1:
                cut = text[:MAX_CHARS].rfind(" ")
            if cut == -1:
                cut = MAX_CHARS
            else:
                cut += 1  # include the period/space
            chunks.append(text[:cut].strip())
            text = text[cut:].strip()
        return chunks

    def _concatenate_mp3s(self, paths: list[Path], output: Path) -> None:
        with open(output, "wb") as out:
            for p in paths:
                out.write(p.read_bytes())

    def list_voices(self) -> list[Voice]:
        return [Voice(id=v, name=v.title(), provider=self.name) for v in self.VOICES]
