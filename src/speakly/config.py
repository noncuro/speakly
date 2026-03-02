"""Config loading/saving and API key management via keyring."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

CONFIG_DIR = Path.home() / ".speakly"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class SpeaklyConfig:
    provider: str = "edge"
    voice: str = ""
    speed: float = 1.0
    llm: str = "none"


def load_config() -> SpeaklyConfig:
    """Read config.toml and return SpeaklyConfig. Returns defaults if no file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        return SpeaklyConfig()

    with open(CONFIG_FILE, "rb") as f:
        data = tomllib.load(f)

    defaults = data.get("defaults", {})
    valid_fields = {f.name for f in fields(SpeaklyConfig)}
    filtered = {k: v for k, v in defaults.items() if k in valid_fields}
    return SpeaklyConfig(**filtered)


def save_config(config: SpeaklyConfig) -> None:
    """Write config.toml with [defaults] section."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "[defaults]",
        f'provider = "{config.provider}"',
        f'voice = "{config.voice}"',
        f"speed = {config.speed}",
        f'llm = "{config.llm}"',
        "",
    ]
    CONFIG_FILE.write_text("\n".join(lines))


def get_api_key(name: str) -> str | None:
    """Check env var first, then keyring. Returns None if not found."""
    env_val = os.environ.get(name)
    if env_val:
        return env_val

    try:
        import keyring

        val = keyring.get_password("speakly", name)
        if val:
            return val
    except Exception:
        pass

    return None


def set_api_key(name: str, value: str) -> None:
    """Store an API key in the system keyring."""
    try:
        import keyring

        keyring.set_password("speakly", name, value)
    except Exception as e:
        print(f"Warning: could not store key in keyring: {e}")
        print("The key will not be persisted between sessions.")
