"""Speakly CLI — text-to-speech with floating mini-player."""

from __future__ import annotations

import subprocess
import sys
import threading
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
    provider: str = typer.Option("inworld", "--provider", "-p", help="TTS provider"),
    voice: str = typer.Option("", "--voice", "-v", help="Voice name/ID"),
    speed: float = typer.Option(2.0, "--speed", "-s", help="Playback speed"),
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

    initial_title = text[:60] + ("..." if len(text) > 60 else "")

    # Check cache before launching player
    cached = get_cached(text, provider, voice or "default")

    # Launch player immediately — with audio if cached, in loading state if not
    _launch_player(
        initial_title=initial_title,
        full_text=text,
        speed=speed,
        audio_path=cached,
        provider=provider,
        voice=voice,
    )


def _generate_audio(provider: str, voice: str, speed: float, text: str, player):
    """Run TTS generation in background thread, then signal player."""
    try:
        p = get_provider(provider)
        path = cache_path(text, provider, voice or "default")
        p.synthesize(text, voice, speed, path)
        player.load_audio(path)
    except Exception as e:
        # Update title to show error
        player.update_title(f"Error: {e}")

    evict_old()


def _launch_player(
    initial_title: str,
    full_text: str,
    speed: float,
    audio_path: Path | None,
    provider: str,
    voice: str,
):
    from PyQt6.QtWidgets import QApplication
    from speakly.player import MiniPlayer

    qt_app = QApplication(sys.argv)
    player = MiniPlayer(initial_title=initial_title, initial_speed=speed, audio_path=audio_path)

    # Generate title in background
    generate_title(full_text, player.update_title)

    # If no cached audio, generate in background thread
    if audio_path is None:
        thread = threading.Thread(
            target=_generate_audio,
            args=(provider, voice, speed, full_text, player),
            daemon=True,
        )
        thread.start()

    player.show()
    sys.exit(qt_app.exec())
