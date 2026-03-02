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
import speakly.providers.edge  # always available (free, no API key)

try:
    import speakly.providers.openai
except ImportError:
    pass
try:
    import speakly.providers.elevenlabs
except ImportError:
    pass
try:
    import speakly.providers.inworld
except ImportError:
    pass

from speakly.cache import cache_path, evict_old, get_cached
from speakly.config import load_config
from speakly.titler import generate_title

app = typer.Typer(
    name="speakly",
    help="Text-to-speech with a floating mini-player.",
    add_completion=False,
)


def _get_clipboard() -> str:
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True)
        return result.stdout.strip()
    except FileNotFoundError:
        # Linux fallback
        for cmd in [
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ]:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True)
                return result.stdout.strip()
            except FileNotFoundError:
                continue
    return ""


@app.command()
def config():
    """Open interactive configuration."""
    from speakly.config_tui import run_config_tui

    run_config_tui()


@app.command(name="install-shortcut")
def install_shortcut_cmd():
    """Install a macOS Quick Action for system-wide keyboard shortcut."""
    from speakly.shortcut import install_shortcut

    path = install_shortcut()
    typer.echo(f"Installed Quick Action to {path}")
    typer.echo()
    typer.echo("To assign a keyboard shortcut:")
    typer.echo("  System Settings > Keyboard > Keyboard Shortcuts > Services > Speakly")
    typer.echo()
    typer.echo("Then: copy text (Cmd+C), press your shortcut — Speakly reads it aloud.")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    text: Optional[str] = typer.Argument(None, help="Text to speak"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="TTS provider"),
    voice: Optional[str] = typer.Option(None, "--voice", "-v", help="Voice name/ID"),
    speed: Optional[float] = typer.Option(None, "--speed", "-s", help="Playback speed"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read text from file"),
    list_voices_flag: bool = typer.Option(False, "--list-voices", help="List available voices"),
):
    if ctx.invoked_subcommand is not None:
        return

    # Typer captures subcommand names as the text argument — re-route
    if text == "config":
        config()
        raise typer.Exit()
    if text == "install-shortcut":
        install_shortcut_cmd()
        raise typer.Exit()

    # Load config for defaults
    cfg = load_config()
    provider = provider or cfg.provider
    voice = voice if voice is not None else cfg.voice
    speed = speed if speed is not None else cfg.speed

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
        llm=cfg.llm,
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
    llm: str = "none",
):
    from PyQt6.QtWidgets import QApplication
    from speakly.player import MiniPlayer

    qt_app = QApplication(sys.argv)
    player = MiniPlayer(initial_title=initial_title, initial_speed=speed, audio_path=audio_path)

    # Generate title in background
    generate_title(full_text, player.update_title, llm=llm)

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
