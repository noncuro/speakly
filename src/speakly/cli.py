"""Speakly CLI — text-to-speech with floating mini-player."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import typer

log = logging.getLogger("speakly.cli")

from speakly import bench

# Import providers to trigger registration
from speakly.providers import get_provider
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
from speakly.sanitize import sanitize
from speakly.progressive_core import PROGRESSIVE_MIN_CHARS, ProgressiveAdapter, ProgressiveCallbacks, ProgressiveOrchestrator
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
    bench_exit: bool = typer.Option(False, "--bench-exit", hidden=True, help="Auto-quit after first play (benchmark mode)"),
):
    bench.mark("process_start")

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
    bench.mark("config_loaded")

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

    text = sanitize(text)
    if not text:
        typer.echo("Text became empty after sanitization (e.g. input was only URLs or images).", err=True)
        raise typer.Exit(1)

    initial_title = text[:60] + ("..." if len(text) > 60 else "")

    log.info("=== Speakly invocation ===")
    log.info("Provider: %s | Voice: %s | Speed: %s", provider, voice, speed)
    log.info("Text length: %d chars", len(text))

    # Check cache before launching player
    cached = get_cached(text, provider, voice or "default")
    log.info("Cache hit: %s (path: %s)", bool(cached), cached)
    bench.mark("cache_check", hit=bool(cached), provider=provider)
    progressive = _should_use_progressive(provider=provider, text=text, cached_path=cached)
    prog_mode = os.environ.get("SPEAKLY_PROGRESSIVE_MODE", "auto")
    log.info(
        "Progressive decision: %s (mode=%s, provider=%s, len=%d, min=%d, cached=%s)",
        progressive, prog_mode, provider, len(text), PROGRESSIVE_MIN_CHARS, bool(cached),
    )
    bench.mark("progressive_decision", mode=prog_mode, progressive=progressive)

    # Launch player immediately — with audio if cached, in loading state if not
    _launch_player(
        initial_title=initial_title,
        full_text=text,
        speed=speed,
        audio_path=cached,
        provider=provider,
        voice=voice,
        llm=cfg.llm,
        progressive=progressive,
        bench_exit=bench_exit,
    )


_PROGRESSIVE_PROVIDERS = {"edge", "openai", "elevenlabs", "inworld"}


def _should_use_progressive(provider: str, text: str, cached_path: Path | None) -> bool:
    mode = os.environ.get("SPEAKLY_PROGRESSIVE_MODE", "auto")
    if mode == "off":
        return False
    if cached_path is not None:
        return False
    if provider not in _PROGRESSIVE_PROVIDERS:
        return False
    if mode == "on":
        return True
    # auto: progressive for long text
    return len(text) >= PROGRESSIVE_MIN_CHARS


def _generate_audio(provider: str, voice: str | None, speed: float, text: str, player):
    """Run TTS generation in background thread, then signal player."""
    try:
        log.info("_generate_audio: starting non-progressive synthesis (provider=%s)", provider)
        bench.mark("synthesis_start", provider=provider)
        p = get_provider(provider)
        path = cache_path(text, provider, voice or "default")
        p.synthesize(text, voice, speed, path)
        log.info("_generate_audio: synthesis complete, signalling player (path=%s)", path)
        bench.mark("synthesis_complete", provider=provider)
        player.load_audio(path)
    except Exception as e:
        log.error("_generate_audio: error: %s", e)
        player.update_title(f"Error: {e}")

    evict_old()


def _get_progressive_adapter(provider: str) -> ProgressiveAdapter:
    """Return the progressive adapter for the given provider."""
    if provider == "edge":
        from speakly.progressive_edge import EdgeProgressiveAdapter
        return EdgeProgressiveAdapter()
    if provider == "openai":
        from speakly.progressive_openai import OpenAIProgressiveAdapter
        return OpenAIProgressiveAdapter()
    if provider == "elevenlabs":
        from speakly.progressive_elevenlabs import ElevenLabsProgressiveAdapter
        return ElevenLabsProgressiveAdapter()
    if provider == "inworld":
        from speakly.progressive_inworld import InworldProgressiveAdapter
        return InworldProgressiveAdapter()
    raise ValueError(f"No progressive adapter for provider '{provider}'")


def _generate_audio_progressive(provider: str, voice: str | None, speed: float, text: str, player):
    """Run progressive synthesis and stream chunks into the player."""
    try:
        log.info("_generate_audio_progressive: called (provider=%s)", provider)
        bench.mark("progressive_start", provider=provider)
        output_path = cache_path(text, provider, voice or "default")
        adapter = _get_progressive_adapter(provider)
        callbacks = ProgressiveCallbacks(
            on_chunk_ready=player.queue_chunk,
            on_status=player.set_progressive_status,
            on_done=lambda p: (bench.mark("progressive_done"), player.mark_progressive_done(p)),
            on_error=player.set_progressive_error,
        )
        orchestrator = ProgressiveOrchestrator(
            adapter=adapter,
            text=text,
            voice=voice or "",
            speed=speed,
            output_path=output_path,
            callbacks=callbacks,
        )
        orchestrator.run()
    except Exception as e:
        player.set_progressive_error(str(e))
        player.update_title(f"Error: {e}")

    evict_old()


def _launch_player(
    initial_title: str,
    full_text: str,
    speed: float,
    audio_path: Path | None,
    provider: str,
    voice: str | None,
    llm: str = "none",
    progressive: bool = False,
    bench_exit: bool = False,
):
    from PyQt6.QtWidgets import QApplication

    from speakly.dock import configure_dock_icon, configure_dock_name
    from speakly.player import MiniPlayer

    configure_dock_name()  # Must be BEFORE QApplication()

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Speakly")
    qt_app.setApplicationDisplayName("Speakly")
    configure_dock_icon()  # Must be AFTER QApplication()

    player = MiniPlayer(
        initial_title=initial_title,
        initial_speed=speed,
        audio_path=audio_path,
        progressive_mode=progressive and audio_path is None,
        bench_exit=bench_exit,
        provider=provider,
    )

    # Generate title in background
    generate_title(full_text, player.update_title, llm=llm)

    # If no cached audio, generate in background thread
    if audio_path is None:
        target = _generate_audio_progressive if progressive else _generate_audio
        thread = threading.Thread(
            target=target,
            args=(provider, voice, speed, full_text, player),
            daemon=True,
        )
        thread.start()

    player.show()
    bench.mark("player_shown")
    sys.exit(qt_app.exec())
