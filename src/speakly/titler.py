"""Async title generation using Claude Haiku."""

from __future__ import annotations

import os
import threading
from typing import Callable

import anthropic


def generate_title(text: str, callback: Callable[[str], None]) -> threading.Thread:
    """Generate a short title in a background thread and call callback with result."""
    def _run():
        try:
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            snippet = text[:500]
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=30,
                messages=[{
                    "role": "user",
                    "content": f"Generate a 3-6 word title for this text. Reply with ONLY the title, no quotes or punctuation:\n\n{snippet}",
                }],
            )
            title = response.content[0].text.strip().strip('"\'')
            callback(title)
        except Exception:
            # Silently fail — placeholder title stays
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
