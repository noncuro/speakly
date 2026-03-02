"""Sanitize text for TTS — strip URLs, markdown syntax, and normalize whitespace."""

from __future__ import annotations

import re


def sanitize(text: str) -> str:
    """Clean text for a better listening experience.

    Processing order matters: markdown links before bare URLs so we keep link text.
    """
    # Markdown images ![alt](url) → remove entirely
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)

    # Markdown links [text](url) → keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Standalone URLs (http/https/www)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)

    # Horizontal rules: lines that are only ---, ***, or ___ (before bold/italic!)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Bold/italic: **text**, __text__, *text*, _text_
    # Handle bold first (** / __) before italic (* / _)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", text)

    # Strikethrough: ~~text~~ → keep text
    text = re.sub(r"~~(.+?)~~", r"\1", text)

    # Headings: strip leading # markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Code fences: remove ``` lines (keep content between them)
    text = re.sub(r"^```[^\n]*$", "", text, flags=re.MULTILINE)

    # Inline code: `code` → keep code
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Bullet markers: leading - / * / + / 1. (keep text)
    text = re.sub(r"^(\s*)[*\-+]\s+", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)\d+\.\s+", r"\1", text, flags=re.MULTILINE)

    # Blockquote markers: leading >
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

    # Collapse multiple blank lines into one
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove leading/trailing whitespace per line, then overall
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return text.strip()
