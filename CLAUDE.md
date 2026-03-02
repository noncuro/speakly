# Speakly

Text-to-speech mini-player — converts text to speech via multiple TTS providers and plays it in a floating PyQt6 mini-player with full playback controls.

## Tech Stack

- **Language**: Python 3.11+
- **Package manager**: uv
- **CLI framework**: Typer
- **GUI**: PyQt6 (QMediaPlayer + floating window)
- **TTS providers**: edge-tts (free default), OpenAI, ElevenLabs, Inworld
- **Title generation**: Anthropic or OpenAI via raw httpx (optional), heuristic fallback
- **Secrets**: macOS Keychain via `keyring`, or environment variables

## Commands

```bash
uv run speakly "text to speak"          # Speak text (free edge-tts, no API key)
uv run speakly --provider inworld       # Use specific provider
uv run speakly --voice nova             # Specify voice
uv run speakly --speed 1.5              # Set playback speed
uv run speakly --file doc.txt           # Read from file
uv run speakly                          # Read from clipboard
uv run speakly --list-voices            # List voices
uv run speakly config                   # Interactive config setup
uv sync                                 # Install dependencies
```

Default provider is edge-tts at 1x speed. Run `speakly config` to change defaults.

## Architecture

**Flow:** Keyboard shortcut / CLI → player shows instantly (loading state) → TTS in background → auto-play when ready

- **Instant player**: Window appears immediately with loading indicator; TTS runs in background thread
- **File-then-play**: Audio saved to cache file, then played with `QMediaPlayer` for pause/resume/scrub/speed
- **Caching**: Audio cached by SHA256 of (text + provider + voice) in `~/.speakly/cache/`, 7-day eviction
- **Title generation**: LLM call (if configured) fired in parallel with TTS, heuristic fallback if no LLM key
- **Cache hits**: Player opens and plays immediately — no loading state
- **Config**: `~/.speakly/config.toml` for preferences, `keyring` for API keys

## Project Structure

```
speakly/
├── src/speakly/
│   ├── __init__.py
│   ├── cli.py              # Typer CLI entrypoint + orchestration
│   ├── config.py           # Config loading/saving, keyring API key management
│   ├── config_tui.py       # Interactive config TUI (rich prompts)
│   ├── providers/
│   │   ├── __init__.py     # TTSProvider protocol + decorator registry
│   │   ├── edge.py         # edge-tts (free, no API key, default)
│   │   ├── openai.py       # OpenAI TTS (tts-1-hd, raw httpx, 4096-char chunking)
│   │   ├── elevenlabs.py   # ElevenLabs (eleven_multilingual_v2)
│   │   └── inworld.py      # Inworld TTS 1.5 Max (2000-char chunking)
│   ├── player.py           # PyQt6 floating mini-player (always-on-top, dark theme)
│   ├── titler.py           # Multi-LLM title gen (Anthropic/OpenAI via httpx, heuristic fallback)
│   └── cache.py            # SHA256-based audio file caching
├── pyproject.toml
├── LICENSE
├── .gitignore
├── README.md
└── CLAUDE.md
```

## Player Controls

- Play/pause, rewind/forward 10s
- Scrub bar with time display
- Speed buttons: 1x, 1.5x, 2x, 3x
- Volume slider
- Draggable frameless window (~420x140px)
- Catppuccin Mocha dark theme
- Loading state with indeterminate progress bar while TTS generates

## Provider Notes

| Provider | Model | Speed Range | Voice Default | API Key |
|----------|-------|-------------|---------------|---------|
| edge (default) | Microsoft Edge TTS | player speed only | en-US-AriaNeural | None needed |
| OpenAI | tts-1-hd | 0.25-4.0x | nova | Required |
| ElevenLabs | eleven_multilingual_v2 | 1x only (use player speed) | Rachel | Required |
| Inworld | inworld-tts-1.5-max | player speed only | Alex | Required |

- All providers use raw httpx — no SDK dependencies
- OpenAI chunks text at 4096 chars and concatenates MP3s
- ElevenLabs resolves voice names to IDs via API
- Inworld chunks at 2000 chars, uses Basic auth (JWT key:secret base64-encoded)

## API Keys

API keys are stored in **macOS Keychain** via the `keyring` library. Run `speakly config` to set them up interactively, or set environment variables directly.

| Env Var | Provider |
|---------|----------|
| `OPENAI_API_KEY` | OpenAI TTS + title generation |
| `ELEVEN_API_KEY` | ElevenLabs |
| `INWORLD_JWT_KEY` | Inworld |
| `INWORLD_JWT_SECRET` | Inworld |
| `ANTHROPIC_API_KEY` | Title generation (optional) |

Key resolution order: environment variable → keyring → not set.

## Raycast Integration

`~/raycast-scripts/speakly.sh` — reads clipboard and launches Speakly in background.
