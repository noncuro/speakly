"""Speakly CLI — text-to-speech with floating mini-player."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

# Import providers to trigger registration
from speakly.providers import get_provider, list_providers
import speakly.providers.openai
import speakly.providers.elevenlabs
import speakly.providers.inworld

from speakly.cache import cache_path, evict_old, get_cached
from speakly.titler import generate_title

app = typer.Typer(
    name="speakly",
    help="Text-to-speech with a floating mini-player.",
    add_completion=False,
)


def _get_clipboard() -> str:
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout.strip()


@app.callback(invoke_without_command=True)
def main(
    text: Optional[str] = typer.Argument(None, help="Text to speak"),
    provider: str = typer.Option("openai", "--provider", "-p", help="TTS provider"),
    voice: str = typer.Option("", "--voice", "-v", help="Voice name/ID"),
    speed: float = typer.Option(1.0, "--speed", "-s", help="Playback speed"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read text from file"),
    list_voices_flag: bool = typer.Option(False, "--list-voices", help="List available voices"),
):
    if list_voices_flag:
        p = get_provider(provider)
        for v in p.list_voices():
            typer.echo(f"  {v.id:30s} {v.name}")
        raise typer.Exit()

    # Resolve text
    if file:
        text = file.read_text()
    elif not text:
        text = _get_clipboard()
    if not text:
        typer.echo("No text provided. Pass text as argument, --file, or copy to clipboard.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Provider: {provider} | Speed: {speed}x")

    # Check cache
    cached = get_cached(text, provider, voice or "default")
    if cached:
        typer.echo("Cache hit — skipping TTS generation")
        audio_path = cached
    else:
        typer.echo("Generating speech...")
        p = get_provider(provider)
        audio_path = cache_path(text, provider, voice or "default")
        p.synthesize(text, voice, speed, audio_path)
        typer.echo(f"Audio saved: {audio_path}")

    # Evict old cache entries in background
    evict_old()

    # Truncated text as initial title
    initial_title = text[:60] + ("..." if len(text) > 60 else "")

    # Launch player
    _launch_player(audio_path, initial_title, text, speed)


def _launch_player(audio_path: Path, initial_title: str, full_text: str, speed: float):
    from PyQt6.QtWidgets import QApplication
    from speakly.player import MiniPlayer

    qt_app = QApplication(sys.argv)
    player = MiniPlayer(audio_path, initial_title, initial_speed=speed)

    # Generate title in background
    generate_title(full_text, player.update_title)

    player.show()
    sys.exit(qt_app.exec())
