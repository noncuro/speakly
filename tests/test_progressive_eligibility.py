"""Tests for progressive mode eligibility logic."""

from pathlib import Path

from speakly.cli import _should_use_progressive, _PROGRESSIVE_PROVIDERS, PROGRESSIVE_MIN_CHARS


def test_known_providers_eligible():
    """All known progressive providers should be eligible in auto mode with long text."""
    long_text = "x" * (PROGRESSIVE_MIN_CHARS + 1)
    for provider in _PROGRESSIVE_PROVIDERS:
        assert _should_use_progressive(provider, long_text, None) is True


def test_unknown_provider_falls_back():
    """Custom/unknown providers should return False, not raise."""
    long_text = "x" * (PROGRESSIVE_MIN_CHARS + 1)
    assert _should_use_progressive("custom-provider", long_text, None) is False
    assert _should_use_progressive("my-plugin", long_text, None) is False


def test_cached_path_skips_progressive():
    """If audio is already cached, progressive should be skipped."""
    long_text = "x" * (PROGRESSIVE_MIN_CHARS + 1)
    assert _should_use_progressive("edge", long_text, Path("/tmp/cached.mp3")) is False


def test_short_text_skips_in_auto():
    """Short text should not trigger progressive in auto mode."""
    assert _should_use_progressive("edge", "hello", None) is False
