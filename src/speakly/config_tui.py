"""Interactive config TUI using Rich prompts."""

from __future__ import annotations

import os

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from speakly.config import (
    get_api_key,
    load_config,
    save_config,
    set_api_key,
)

console = Console()

API_KEYS = [
    "OPENAI_API_KEY",
    "ELEVEN_API_KEY",
    "INWORLD_JWT_KEY",
    "INWORLD_JWT_SECRET",
    "ANTHROPIC_API_KEY",
]

PROVIDER_CHOICES = ["edge", "openai", "elevenlabs", "inworld"]
LLM_CHOICES = ["none", "anthropic", "openai", "auto"]


def _key_status(name: str) -> str:
    """Return a human-readable status string for an API key."""
    if os.environ.get(name):
        return "[green]set[/green] (env)"

    try:
        import keyring

        val = keyring.get_password("speakly", name)
        if val:
            return "[green]set[/green] (keyring)"
    except Exception:
        pass

    return "[red]not set[/red]"


def run_config_tui() -> None:
    """Walk through interactive Speakly configuration."""
    config = load_config()

    # Show current config
    current = (
        f"  provider: [cyan]{config.provider}[/cyan]\n"
        f"  voice:    [cyan]{config.voice or '(default)'}[/cyan]\n"
        f"  speed:    [cyan]{config.speed}[/cyan]\n"
        f"  llm:      [cyan]{config.llm}[/cyan]"
    )
    console.print(Panel(current, title="Current Config", border_style="dim"))
    console.print()

    # Provider
    config.provider = Prompt.ask(
        "Default TTS provider",
        choices=PROVIDER_CHOICES,
        default=config.provider,
    )

    # Voice
    config.voice = Prompt.ask(
        "Default voice (empty for provider default)",
        default=config.voice or "",
    )

    # Speed
    speed_str = Prompt.ask(
        "Default playback speed",
        default=str(config.speed),
    )
    try:
        config.speed = float(speed_str)
    except ValueError:
        console.print("[yellow]Invalid speed, keeping current value.[/yellow]")

    # LLM
    config.llm = Prompt.ask(
        "Title generation LLM",
        choices=LLM_CHOICES,
        default=config.llm,
    )

    console.print()

    # API keys
    for key_name in API_KEYS:
        status = _key_status(key_name)
        console.print(f"  {key_name}: {status}")

        if Confirm.ask(f"  Set/update {key_name}?", default=False):
            value = Prompt.ask(f"  Enter {key_name}", password=True)
            if value:
                set_api_key(key_name, value)
                console.print(f"  [green]Saved {key_name} to keyring.[/green]")
        console.print()

    # Save
    save_config(config)

    # Summary
    summary = (
        f"  provider: [cyan]{config.provider}[/cyan]\n"
        f"  voice:    [cyan]{config.voice or '(default)'}[/cyan]\n"
        f"  speed:    [cyan]{config.speed}[/cyan]\n"
        f"  llm:      [cyan]{config.llm}[/cyan]"
    )
    console.print(Panel(summary, title="Config Saved", border_style="green"))
