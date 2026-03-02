"""Async title generation using LLM or heuristic fallback."""

from __future__ import annotations

import os
import threading
from typing import Callable

import httpx


_TITLE_PROMPT = (
    "Generate a 3-6 word title for this text. "
    "Reply with ONLY the title, no quotes or punctuation:\n\n"
)


def _get_api_key(env_var: str) -> str | None:
    """Return an API key from env or speakly.config (if available)."""
    key = os.environ.get(env_var)
    if key:
        return key
    try:
        from speakly.config import get_api_key
        return get_api_key(env_var)
    except Exception:
        return None


def _anthropic_title(snippet: str, prompt: str) -> str | None:
    """Generate title via raw Anthropic Messages API."""
    api_key = _get_api_key("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 30,
            "messages": [{"role": "user", "content": f"{prompt}{snippet}"}],
        },
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()["content"][0]["text"].strip().strip("\"'")


def _openai_title(snippet: str, prompt: str) -> str | None:
    """Generate title via raw OpenAI Chat Completions API."""
    api_key = _get_api_key("OPENAI_API_KEY")
    if not api_key:
        return None
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 30,
            "messages": [{"role": "user", "content": f"{prompt}{snippet}"}],
        },
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip().strip("\"'")


def _heuristic_title(text: str) -> str:
    """Return the first 6 words of the text, title-cased, with '...' if truncated."""
    words = text.split()
    truncated = len(words) > 6
    title = " ".join(words[:6]).title()
    if truncated:
        title += "..."
    return title


def _get_title(text: str, llm: str) -> str:
    """Resolve a title using the chosen strategy, falling back to heuristic."""
    snippet = text[:500]
    prompt = _TITLE_PROMPT

    if llm == "anthropic":
        try:
            title = _anthropic_title(snippet, prompt)
            if title:
                return title
        except Exception:
            pass
        return _heuristic_title(text)

    if llm == "openai":
        try:
            title = _openai_title(snippet, prompt)
            if title:
                return title
        except Exception:
            pass
        return _heuristic_title(text)

    if llm == "auto":
        # Try Anthropic first, then OpenAI, then heuristic
        for fn in (_anthropic_title, _openai_title):
            try:
                title = fn(snippet, prompt)
                if title:
                    return title
            except Exception:
                continue
        return _heuristic_title(text)

    # llm == "none" or any unrecognised value
    return _heuristic_title(text)


def generate_title(
    text: str,
    callback: Callable[[str], None],
    llm: str = "none",
) -> threading.Thread:
    """Generate a short title in a background thread and call callback with result."""

    def _run() -> None:
        try:
            title = _get_title(text, llm)
            callback(title)
        except Exception:
            # Last resort — should not happen since _get_title catches internally,
            # but ensures callback fires with *something*.
            callback(_heuristic_title(text))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
