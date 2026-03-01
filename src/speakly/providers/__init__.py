"""TTS provider abstraction and registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class Voice:
    id: str
    name: str
    provider: str


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    def synthesize(self, text: str, voice: str, speed: float, output_path: Path) -> Path:
        """Generate speech audio and save to output_path. Returns the path."""
        ...

    def list_voices(self) -> list[Voice]:
        """Return available voices for this provider."""
        ...


_registry: dict[str, type[TTSProvider]] = {}


def register(name: str):
    """Decorator to register a TTS provider class."""
    def wrapper(cls):
        _registry[name] = cls
        return cls
    return wrapper


def get_provider(name: str) -> TTSProvider:
    """Instantiate and return a registered provider by name."""
    if name not in _registry:
        available = ", ".join(_registry.keys())
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")
    return _registry[name]()


def list_providers() -> list[str]:
    return list(_registry.keys())
